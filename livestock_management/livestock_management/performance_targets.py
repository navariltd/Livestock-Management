"""Age targets applied to already permission-scoped batch report results."""

from frappe.utils import date_diff, getdate

from livestock_management.livestock_management.doctype.livestock_performance_profile.livestock_performance_profile import (
	target_number,
)


def age_on(day, hatch_date):
	if not hatch_date:
		return None
	age = date_diff(getdate(day), getdate(hatch_date))
	return age if age >= 0 else None


def variance(row, actual_key, target_key, prefix):
	actual, target = row.get(actual_key), row.get(target_key)
	if actual is None or target is None:
		return
	row[prefix + "_variance"] = actual - target
	if target != 0:
		row[prefix + "_variance_percent"] = 100 * (actual - target) / target


def apply_targets(row, batch, profile, populations, intervals, egg_count, notes):
	"""No interpolation or partial target totals; zero and missing remain distinct."""
	hatch = batch.get("lvm_hatch_date")
	if not profile or not hatch:
		notes.append("Targets unavailable: assign a readable submitted profile and Hatch/Birth Date.")
		return
	targets = {int(t.age_days): t for t in profile.targets}

	def lookup(day, metric):
		age = age_on(day, hatch)
		target = targets.get(age)
		return target_number(target.get(metric)) if target is not None else None

	if row.get("weight_date"):
		row["weight_age_days"] = age_on(row["weight_date"], hatch)
		row["target_weight_kg"] = lookup(row["weight_date"], "weight_kg")
		variance(row, "actual_weight", "target_weight_kg", "weight")
		if row["target_weight_kg"] is None:
			notes.append("Weight target unavailable at measurement age.")
	if intervals and row.get("fcr") is not None:
		fcr_targets = [(lookup(i["to_date"], "fcr"), i["gain_kg"]) for i in intervals]
		if all(value is not None for value, _ in fcr_targets):
			row["target_fcr"] = sum(value * gain for value, gain in fcr_targets) / sum(
				gain for _, gain in fcr_targets
			)
			variance(row, "fcr", "target_fcr", "fcr")
		else:
			notes.append("FCR target unavailable at ending measurement age.")
	if not populations or any(pop < 0 for _, pop in populations) or sum(pop for _, pop in populations) <= 0:
		notes.append("Period targets unavailable: invalid or missing population exposure.")
		return
	# Positive population before biological age zero is inconsistent, even if a target is zero.
	active = [(day, pop) for day, pop in populations if pop > 0]
	feed_targets = [(lookup(day, "feed_g"), pop) for day, pop in active]
	if all(value is not None for value, _ in feed_targets):
		row["target_feed_kg"] = sum(value * pop / 1000 for value, pop in feed_targets)
		variance(row, "feed_kg", "target_feed_kg", "feed")
	else:
		notes.append("Period feed target unavailable: an exposed age has no intake target or precedes hatch.")
	if not profile.all_female_laying_flock:
		notes.append("Hen-day yield requires an all-female laying profile.")
		return
	exposure = sum(pop for _, pop in active)
	if egg_count is not None:
		row["egg_count"] = egg_count
		row["hen_day_yield"] = 100 * egg_count / exposure
	egg_targets = [(lookup(day, "egg_yield_percent"), pop) for day, pop in active]
	if all(value is not None for value, _ in egg_targets):
		row["target_hen_day_yield"] = sum(value * pop for value, pop in egg_targets) / exposure
		if row.get("hen_day_yield") is not None:
			row["egg_yield_variance_pp"] = row["hen_day_yield"] - row["target_hen_day_yield"]
	else:
		notes.append("Egg-yield target unavailable: an exposed age has no yield target or precedes hatch.")
