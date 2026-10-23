"""Deterministic alert detection. Input records must already have complete scope/access checks."""

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite

from frappe.utils import add_days, date_diff, flt, get_datetime, getdate

from livestock_management.livestock_management.doctype.livestock_performance_profile.livestock_performance_profile import (
	target_number,
)
from livestock_management.livestock_management.number_card.survival_percentage.survival_percentage import (
	calculate_survival,
)
from livestock_management.livestock_management.performance_targets import age_on


@dataclass(frozen=True)
class Evaluation:
	batch: str
	house: str | None
	state: str
	summary: str
	evidence_date: str
	source_doctype: str = "Batch"
	source_name: str | None = None


def occupancy(movements):
	"""Net same-voucher rows before tracking zero-to-positive changes (valuation Repacks do not reset age)."""
	changes = defaultdict(float)
	for move in movements:
		if not isfinite(flt(move.qty)):
			return None, None
		changes[(get_datetime(move.timestamp), move.voucher_type, move.voucher_no)] += flt(move.qty)
	balance, start = 0.0, None
	for (timestamp, _kind, _name), qty in sorted(changes.items()):
		previous = balance
		balance += qty
		if balance < -0.000001:
			return None, None
		if previous <= 0.000001 < balance:
			start = timestamp
		if balance <= 0.000001:
			start = None
	return balance, start


def latest_valid_weight(weights, movements, occupied_since):
	valid = []
	for weight in weights:
		timestamp = get_datetime(weight.posting_date)
		if occupied_since and timestamp < occupied_since:
			continue
		population = sum(flt(m.qty) for m in movements if get_datetime(m.timestamp) <= timestamp)
		average, sample = flt(weight.actual_weight), flt(weight.sample_size)
		if (
			weight.lvm_weight_uom == "Kg"
			and isfinite(average)
			and average > 0
			and isfinite(sample)
			and 0 < sample <= population
			and sample.is_integer()
		):
			valid.append(weight)
	return max(valid, key=lambda w: (get_datetime(w.posting_date), w.name)) if valid else None


def detect(rule, batch, house, movements, weights, entries, profile, today):
	day = getdate(today)

	def result(state, summary, evidence=day, source=None):
		return Evaluation(
			batch.name,
			house,
			state,
			summary,
			str(getdate(evidence)),
			"Weight Record" if source else "Batch",
			source or batch.name,
		)

	if rule.alert_type == "Mortality":
		yesterday = getdate(add_days(day, -1))
		prior = [m for m in movements if getdate(m.date) <= yesterday]
		value, reason, exposure, deaths = calculate_survival({batch.name: prior}, entries, yesterday)
		if exposure == 0 and deaths == 0:
			return result("Cleared", "No livestock exposure on the completed farm day.", yesterday)
		if value is None:
			return result("Unknown", reason or "Mortality inputs are unavailable.", yesterday)
		rate = 100 * deaths / exposure
		active = deaths >= rule.minimum_deaths and rate >= rule.mortality_percent
		return result(
			"Active" if active else "Cleared",
			f"Daily mortality {rate:.4f}% ({deaths:g} deaths / {exposure:g} animals exposed); thresholds {rule.mortality_percent:g}% and {rule.minimum_deaths:g} deaths.",
			yesterday,
		)
	balance, arrived = occupancy(movements)
	if balance is None:
		return result("Unknown", "Stock has an invalid or negative historical balance.")
	if balance <= 0.000001:
		return result("Cleared", "No livestock currently occupies this house.")
	weight = latest_valid_weight(weights, movements, arrived)
	if rule.alert_type == "Overdue Weighing":
		reference = getdate(weight.posting_date) if weight else getdate(arrived)
		due = getdate(add_days(reference, rule.max_gap_days))
		active = day > due
		return result(
			"Active" if active else "Cleared",
			f"Weighing due {due}; {date_diff(day, reference)} days since {'last valid weight' if weight else 'arrival'}, maximum {rule.max_gap_days} days.",
			reference,
			weight.name if weight else None,
		)
	if not weight:
		return result("Unknown", "No valid kg/animal weight in the current occupancy period.")
	if not profile or not batch.get("lvm_hatch_date"):
		return result("Unknown", "A submitted profile and Hatch/Birth Date are required.")
	age = age_on(weight.posting_date, batch.lvm_hatch_date)
	row = next((r for r in profile.targets if r.age_days == age), None)
	target = target_number(row.weight_kg) if row else None
	if target is None or target <= 0:
		return result("Unknown", "No positive weight target at the measurement age.")
	shortfall = 100 * (target - flt(weight.actual_weight)) / target
	active = shortfall >= rule.weight_shortfall_percent
	return result(
		"Active" if active else "Cleared",
		f"Weight {flt(weight.actual_weight):g} kg/animal versus {target:g} kg target at age {age}; shortfall {shortfall:.4f}%, threshold {rule.weight_shortfall_percent:g}%.",
		weight.posting_date,
		weight.name,
	)


def detect_treatment(diagnosis, house, today):
	day = getdate(today)

	def result(state, summary):
		return Evaluation(
			diagnosis.batch, house, state, summary, str(day), "Veterinary Diagnosis", diagnosis.name
		)

	if diagnosis.docstatus == 2 or diagnosis.status in ("Completed", "Cancelled"):
		return result("Cleared", "Treatment follow-up completed or source diagnosis cancelled.")
	if diagnosis.status != "Pending" or not diagnosis.end_date:
		return result("Unknown", "Pending treatment requires an explicit end date.")
	due = getdate(diagnosis.end_date)
	return result(
		"Active" if due < day else "Cleared",
		f"Overdue treatment follow-up: diagnosis remains Pending; end date {due}. This does not indicate an individually missed dose."
		if due < day
		else f"Treatment follow-up is not overdue; end date {due}.",
	)
