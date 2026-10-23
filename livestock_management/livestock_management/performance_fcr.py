"""Shared measured-interval FCR calculation. Callers supply permission-scoped records."""

from collections import defaultdict
from math import isfinite

from frappe.utils import flt, get_datetime, getdate


def calculate_fcr(movements, weights, entries, rows, from_date, feed_converter):
	groups = defaultdict(lambda: {"moves": [], "weights": [], "feed": []})
	for batch, moves in movements.items():
		for m in moves:
			groups[(batch, m.warehouse)]["moves"].append(m)
	for w in weights:
		groups[(w.batch, w.lvm_livestock_house)]["weights"].append(w)
	details = defaultdict(list)
	for row in rows:
		details[row.parent].append(row)
	for e in entries:
		groups[(e.lvm_batch, e.lvm_livestock_house)]["feed"].append(e)
	total_feed, total_gain, intervals = 0.0, 0.0, []
	for (batch, house), group in groups.items():
		opening = sum(flt(m.qty) for m in group["moves"] if getdate(m.date) < getdate(from_date))
		active = (
			opening > 0
			or group["weights"]
			or group["feed"]
			or any(flt(m.qty) != 0 and getdate(m.date) >= getdate(from_date) for m in group["moves"])
		)
		if not active:
			continue
		ordered = sorted(group["weights"], key=lambda w: (get_datetime(w.posting_date), w.name))
		if len(ordered) < 2:
			return None, "Every active batch/house needs two weight measurements in the selected period.", []
		start, end = ordered[-2:]
		a, b = get_datetime(start.posting_date), get_datetime(end.posting_date)
		population = sum(flt(m.qty) for m in group["moves"] if m.timestamp <= a)
		if a >= b or population <= 0:
			return None, "Weight timestamps must differ and opening population must be positive.", []
		for weight in (start, end):
			if (
				weight.lvm_weight_uom != "Kg"
				or not 0 < flt(weight.actual_weight) < float("inf")
				or not 0 < flt(weight.sample_size) <= population
			):
				return None, "Weights need confirmed average Kg per animal and valid sample sizes.", []
		# Net valuation-only Repacks by voucher. Any real stock movement invalidates this simple estimator.
		net = defaultdict(float)
		for m in group["moves"]:
			if a < m.timestamp <= b:
				net[(m.voucher_type, m.voucher_no)] += flt(m.qty)
		if any(abs(q) > 0.000001 for q in net.values()):
			return None, "Stock moved between measurements; movement-adjusted FCR is not yet supported.", []
		gain = population * (flt(end.actual_weight) - flt(start.actual_weight))
		if not isfinite(gain) or gain <= 0:
			return None, "Total live-weight gain must be positive.", []
		feeding = [e for e in group["feed"] if a < get_datetime(f"{e.posting_date} {e.posting_time}") <= b]
		if not feeding or any(not details[e.name] for e in feeding):
			return None, "No complete feeding records exist between the measurements.", []
		kg, reason = feed_converter([row for e in feeding for row in details[e.name]], precision=None)
		if kg is None:
			return None, reason, []
		total_feed += kg
		total_gain += gain
		intervals.append(
			{
				"batch": batch,
				"warehouse": house,
				"from_date": str(a),
				"to_date": str(b),
				"feed_kg": kg,
				"gain_kg": gain,
			}
		)
	if total_gain <= 0:
		return None, "No valid measured intervals are available.", []
	return round(total_feed / total_gain, 2), None, intervals
