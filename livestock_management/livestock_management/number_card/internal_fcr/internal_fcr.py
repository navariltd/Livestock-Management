# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

"""Latest measured interval FCR, aggregated by feed kg / biomass gain kg."""

from collections import defaultdict
from math import isfinite

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, get_first_day, getdate, nowdate

from livestock_management.livestock_management.batch_stock import get_batch_movements
from livestock_management.livestock_management.dashboard_chart_source.daily_population.daily_population import (
	validate_scope,
)
from livestock_management.livestock_management.number_card.feed_consumed.feed_consumed import sum_feed_kg


@frappe.whitelist()
def get(filters: str | dict | list | None = None) -> dict:
	parsed = frappe.parse_json(filters) if isinstance(filters, str) else filters
	if parsed is None or parsed == []:
		parsed = {}
	if not isinstance(parsed, dict):
		raise frappe.ValidationError(_("Invalid FCR filters."))
	scope = dict(parsed)
	scope["company"] = scope.get("company") or frappe.defaults.get_user_default("Company")
	if not scope["company"]:
		frappe.throw(_("Set a default Company or select Company in the card filters."))
	scope["to_date"] = getdate(scope.get("to_date") or nowdate())
	scope["from_date"] = getdate(scope.get("from_date") or get_first_day(scope["to_date"]))
	if scope["from_date"] > scope["to_date"] or scope["to_date"] > getdate(nowdate()):
		frappe.throw(_("Select a historical date range with From Date on or before To Date."))
	validate_scope(scope)
	for doctype in ("Stock Entry", "Weight Record"):
		frappe.has_permission(doctype, "read", throw=True)
	item_filters = {"is_stock_item": 1, "has_batch_no": 1, "stock_uom": ["in", ["Nos", "Unit"]]}
	if scope.get("item_code"):
		item_filters["name"] = scope["item_code"]
	items = frappe.get_list("Item", filters=item_filters, pluck="name", limit_page_length=0)
	batch_filters = {"lvm_is_livestock_item": 1, "item": ["in", items]}
	if scope.get("batch"):
		batch_filters["name"] = scope["batch"]
	batches = (
		frappe.get_list("Batch", filters=batch_filters, pluck="name", limit_page_length=0) if items else []
	)
	if not batches:
		return response(None, scope, "No eligible livestock batches.")
	scope["item_codes"] = items
	warehouses = frappe.get_list(
		"Warehouse", filters={"company": scope["company"], "is_group": 0}, pluck="name", limit_page_length=0
	)
	moves = get_batch_movements(scope, batches)
	# Do not filter out unknown weight units/houses: doing so could select older records silently.
	weights = frappe.get_list(
		"Weight Record",
		filters={
			"batch": ["in", batches],
			"lvm_company": scope["company"],
			"docstatus": ["<", 2],
			"posting_date": ["between", [str(scope["from_date"]), str(add_days(scope["to_date"], 1))]],
		},
		fields=[
			"name",
			"batch",
			"posting_date",
			"actual_weight",
			"sample_size",
			"lvm_weight_uom",
			"lvm_livestock_house",
		],
		order_by="posting_date asc, creation asc, name asc",
		limit_page_length=0,
	)
	# BETWEEN includes next midnight: exclude it explicitly to preserve the selected end date.
	weights = [w for w in weights if getdate(w.posting_date) <= scope["to_date"]]
	entries = frappe.get_list(
		"Stock Entry",
		filters={
			"company": scope["company"],
			"docstatus": 1,
			"purpose": "Material Issue",
			"stock_entry_type": "Feeding",
			"lvm_batch": ["in", batches],
			"posting_date": ["between", [scope["from_date"], scope["to_date"]]],
		},
		fields=["name", "lvm_batch", "lvm_livestock_house", "posting_date", "posting_time"],
		limit_page_length=0,
	)
	for row in [*weights, *entries]:
		if not row.lvm_livestock_house or row.lvm_livestock_house not in warehouses:
			return response(
				None, scope, "Weights and feeding entries require an accessible, explicit livestock house."
			)
	if scope.get("warehouse"):
		weights = [w for w in weights if w.lvm_livestock_house == scope["warehouse"]]
		entries = [e for e in entries if e.lvm_livestock_house == scope["warehouse"]]
	rows = (
		frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": ["in", [e.name for e in entries]]},
			fields=["parent", "item_code", "stock_uom", "transfer_qty", "s_warehouse", "t_warehouse"],
			limit_page_length=0,
		)
		if entries
		else []
	)
	feed_items = (
		frappe.get_list(
			"Item",
			filters={"name": ["in", list({r.item_code for r in rows})]},
			pluck="name",
			limit_page_length=0,
		)
		if rows
		else []
	)
	if any(r.item_code not in feed_items or r.s_warehouse not in warehouses for r in rows):
		return response(None, scope, "Some feed details are inaccessible.")
	value, reason, intervals = calculate_fcr(moves, weights, entries, rows, scope["from_date"])
	return response(value, scope, reason, intervals)


def calculate_fcr(movements, weights, entries, rows, from_date):
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
		kg, reason = sum_feed_kg([row for e in feeding for row in details[e.name]], precision=None)
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


def response(value, scope, reason, intervals=None):
	return {
		"value": value,
		"fieldtype": "Float",
		"precision": 2,
		"uom": "kg feed / kg live-weight gain",
		"reason": _(reason) if reason else None,
		"intervals": intervals or [],
		"route": ["List", "Weight Record", "List"],
		"route_options": {
			"lvm_company": scope["company"],
			"posting_date": ["between", [str(scope["from_date"]), str(add_days(scope["to_date"], 1))]],
			**({"batch": scope["batch"]} if scope.get("batch") else {}),
			**({"lvm_livestock_house": scope["warehouse"]} if scope.get("warehouse") else {}),
		},
	}
