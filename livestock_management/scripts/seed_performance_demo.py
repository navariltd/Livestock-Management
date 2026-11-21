"""Explicit, CLI-only demo data for performance targets. Never invoked by installation or migration.

Creates a broiler Livestock Performance Profile (weekly ages, daily mortality filled from
cumulative breed-guide style figures) and one hatched batch with placement, daily feeding,
mortality and weighings, so the Livestock Batch Performance report shows weight, feed, FCR
and mortality targets side by side.

Preview (default, writes nothing):
  bench --site SITE execute livestock_management.scripts.seed_performance_demo.populate \
    --kwargs '{"company":"Navari Demo"}'
Write:
  bench --site SITE execute livestock_management.scripts.seed_performance_demo.populate \
    --kwargs '{"company":"Navari Demo","dry_run":0}'

Submitted Stock Entries affect inventory and accounting. Use a demo/test company. Re-running for
the same company and end_date reuses the records it already created.
"""

from math import floor

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from livestock_management.livestock_management.doctype.livestock_performance_profile.livestock_performance_profile import (
	daily_mortality_from_cumulative,
	days_to_weeks,
)

PREFIX = "PERF-DEMO"
FLOCK_AGE = 21  # flock age in days on end_date
PLACED = 1000
TARGET_DAYS = 42
SAMPLE_SIZE = 50
BIRD_RATE = 120
FEED_RATE = 60

# Generic broiler curve used for demonstration, not a specific breed's published guide.
WEIGHT_KG = {0: 0.042, 7: 0.19, 14: 0.48, 21: 0.93, 28: 1.5, 35: 2.1, 42: 2.7}
FEED_G = {0: 12, 7: 35, 14: 75, 21: 115, 28: 150, 35: 180, 42: 200}
FCR = {0: 0.8, 7: 0.9, 14: 1.1, 21: 1.3, 28: 1.45, 35: 1.6, 42: 1.75}
CUMULATIVE_MORTALITY = [(0, 0.3), (7, 1.0), (14, 1.6), (21, 2.2), (28, 2.9), (35, 3.6), (42, 4.3)]

# Actual performance relative to target, so the report shows non-zero variances.
FEED_FACTOR = 1.04
WEIGHT_FACTOR = 0.96
MORTALITY_FACTOR = 1.25

# The final two weighings are consecutive days with no deaths between them: the report's
# Interval FCR is unavailable when any stock moves between the last two measurements.
WEIGHING_DAYS = (7, 14, 20, 21)
NO_DEATH_DAYS = {20}
FEED_RECEIPT, PLACEMENT, WEIGH, FEED, DEATHS = "05:00:00", "06:00:00", "06:30:00", "12:00:00", "18:00:00"


def interpolate(anchors, day):
	days = sorted(anchors)
	if day in anchors:
		return anchors[day]
	low = max(d for d in days if d < day)
	high = min(d for d in days if d > day)
	return anchors[low] + (anchors[high] - anchors[low]) * (day - low) / (high - low)


def target_rows():
	mortality = daily_mortality_from_cumulative(range(TARGET_DAYS + 1), CUMULATIVE_MORTALITY)
	return [
		{
			"age_days": day,
			"age_weeks": days_to_weeks(day),
			"weight_kg": f"{interpolate(WEIGHT_KG, day):.3f}",
			"feed_g": f"{interpolate(FEED_G, day):.1f}",
			"fcr": f"{interpolate(FCR, day):.3f}",
			"mortality_percent": str(mortality[day]),
		}
		for day in range(TARGET_DAYS + 1)
	]


def plan(company, end_date):
	"""Deterministic schedule: stable keys and times make re-runs for the same end_date repeat-safe."""
	end = getdate(end_date)
	hatch = getdate(add_days(end, -FLOCK_AGE))
	targets = {row["age_days"]: row for row in target_rows()}
	population, carry, days = PLACED, 0.0, []
	for age in range(FLOCK_AGE + 1):
		day = getdate(add_days(hatch, age))
		feed_kg = round(float(targets[age]["feed_g"]) / 1000 * population * FEED_FACTOR, 2)
		carry += population * float(targets[age]["mortality_percent"]) / 100 * MORTALITY_FACTOR
		deaths = 0 if age in NO_DEATH_DAYS else floor(carry)
		carry -= deaths
		weight = None
		if age in WEIGHING_DAYS:
			weight = round(float(targets[age]["weight_kg"]) * WEIGHT_FACTOR, 3)
		days.append(
			frappe._dict(
				age=age, date=day, population=population, feed_kg=feed_kg, deaths=deaths, weight_kg=weight
			)
		)
		population -= deaths
	abbr = frappe.db.get_value("Company", company, "abbr")
	return frappe._dict(
		company=company,
		hatch=hatch,
		end=end,
		item=f"{PREFIX} Broiler",
		feed_item=f"{PREFIX} Broiler Feed",
		batch=f"{PREFIX}-{hatch.strftime('%Y%m%d')}",
		house=f"{PREFIX} House - {abbr}",
		feed_store=f"{PREFIX} Feed Store - {abbr}",
		profile_name=f"{PREFIX} Broiler Targets",
		targets=list(targets.values()),
		days=days,
		feed_stock_kg=round(sum(d.feed_kg for d in days) * 1.1, 0),
		closing_population=population,
	)


def populate(company, dry_run=1, end_date=None, employee=None):
	"""Preview by default. CLI commits on success; failures roll back this script's writes."""
	if str(dry_run) not in ("0", "1"):
		frappe.throw(_("dry_run must be 0 or 1."))
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("System Manager access is required to create performance demo data."))
	frappe.get_doc("Company", company).check_permission("read")
	end_date = getdate(end_date or add_days(nowdate(), -1))
	if end_date >= getdate(nowdate()):
		frappe.throw(_("end_date must be before today so no demo entry is posted in the future."))
	for doctype, field in (
		("Livestock Performance Target", "mortality_percent"),
		("Batch", "lvm_hatch_date"),
	):
		if not frappe.db.has_column(doctype, field):
			frappe.throw(_("Run site migration first: {0} has no {1} column.").format(doctype, field))
	setup = plan(company, end_date)
	summary = preview(setup)
	if str(dry_run) == "1":
		return {"dry_run": 1, **summary}
	setup.update(prerequisites(company, employee))
	savepoint = "perf_demo"
	frappe.db.savepoint(savepoint)
	try:
		write(setup)
		summary["report"] = verify(setup)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise
	return {"dry_run": 0, **summary}


def preview(setup):
	return {
		"company": setup.company,
		"batch": setup.batch,
		"hatch_date": str(setup.hatch),
		"end_date": str(setup.end),
		"placed": PLACED,
		"deaths": sum(d.deaths for d in setup.days),
		"closing_population": setup.closing_population,
		"feed_kg": round(sum(d.feed_kg for d in setup.days), 2),
		"weighings": {d.age: d.weight_kg for d in setup.days if d.weight_kg},
		"profile": setup.profile_name,
		"weekly_targets": [row for row in setup.targets if row["age_days"] % 7 == 0],
		"stock_entries": 2 + len(setup.days) + sum(1 for d in setup.days if d.deaths),
		"report_filters": {
			"company": setup.company,
			"from_date": str(setup.hatch),
			"to_date": str(setup.end),
			"batch": setup.batch,
			"age_unit": "Weeks",
		},
	}


def prerequisites(company, employee):
	values = frappe.db.get_value(
		"Company", company, ["stock_adjustment_account", "cost_center", "default_currency"], as_dict=True
	)
	group = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name", order_by="lft asc")
	if not (values.stock_adjustment_account and values.cost_center and group):
		frappe.throw(_("Configure a group Warehouse, stock adjustment account and Cost Center first."))
	if employee:
		if frappe.db.get_value("Employee", employee, ["company", "status"]) != (company, "Active"):
			frappe.throw(_("Employee must be active and belong to the demo Company."))
	else:
		employee = frappe.db.get_value("Employee", {"company": company, "status": "Active"}, "name")
		if not employee:
			frappe.throw(_("Provide an active Employee in the demo Company to record weighings."))
	item_groups = {}
	for preferred in ("Livestock", "Feeds"):
		item_groups[preferred] = (
			preferred
			if frappe.db.get_value("Item Group", {"name": preferred, "is_group": 0})
			else frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		)
	return frappe._dict(
		account=values.stock_adjustment_account,
		cost_center=values.cost_center,
		warehouse_group=group,
		employee=employee,
		item_groups=item_groups,
	)


def ensure(doctype, filters, values, submit=False):
	"""Reuse a matching demo record; never overwrite one that differs or is not in the expected state."""
	name = frappe.db.get_value(doctype, filters, "name")
	if name:
		doc = frappe.get_doc(doctype, name)
		if submit and doc.docstatus != 1:
			frappe.throw(
				_("Existing demo {0} {1} is not submitted; refusing to reuse it.").format(doctype, name)
			)
		return doc
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert()
	if submit:
		doc.submit()
	return doc


def write(setup):
	ensure(
		"Warehouse",
		{"name": setup.house},
		{
			"warehouse_name": f"{PREFIX} House",
			"company": setup.company,
			"parent_warehouse": setup.warehouse_group,
		},
	)
	ensure(
		"Warehouse",
		{"name": setup.feed_store},
		{
			"warehouse_name": f"{PREFIX} Feed Store",
			"company": setup.company,
			"parent_warehouse": setup.warehouse_group,
		},
	)
	ensure(
		"Item",
		{"name": setup.item},
		{
			"item_code": setup.item,
			"item_name": setup.item,
			"item_group": setup.item_groups["Livestock"],
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"has_batch_no": 1,
			"has_serial_no": 0,
			"create_new_batch": 0,
			"description": "Demo broiler flock for performance targets.",
		},
	)
	ensure(
		"Item",
		{"name": setup.feed_item},
		{
			"item_code": setup.feed_item,
			"item_name": setup.feed_item,
			"item_group": setup.item_groups["Feeds"],
			"stock_uom": "Kg",
			"is_stock_item": 1,
			"description": "Demo broiler feed.",
		},
	)
	profile = ensure(
		"Livestock Performance Profile",
		{"profile_name": setup.profile_name, "docstatus": ["<", 2]},
		{"profile_name": setup.profile_name, "all_female_laying_flock": 0, "targets": setup.targets},
		submit=True,
	)
	batch = ensure(
		"Batch",
		{"name": setup.batch},
		{
			"batch_id": setup.batch,
			"item": setup.item,
			"manufacturing_date": setup.hatch,
			"lvm_hatch_date": setup.hatch,
			"lvm_performance_profile": profile.name,
			"lvm_is_livestock_item": 1,
			"lvm_location": setup.house,
			# Closed: demo feeding must not create capitalisation Repacks.
			"lvm_capitalisation_status": "Closed",
		},
	)
	if batch.lvm_performance_profile != profile.name or str(batch.lvm_hatch_date) != str(setup.hatch):
		frappe.throw(
			_("Existing demo Batch {0} differs from the plan; refusing to reuse it.").format(batch.name)
		)

	def row(item, qty, uom, source=None, target=None, rate=None, batch_no=None):
		values = {
			"item_code": item,
			"qty": qty,
			"uom": uom,
			"stock_uom": uom,
			"conversion_factor": 1,
			"s_warehouse": source,
			"t_warehouse": target,
			"expense_account": setup.account,
			"cost_center": setup.cost_center,
		}
		if rate is not None:
			values.update(basic_rate=rate, set_basic_rate_manually=1)
		if batch_no:
			values.update(batch_no=batch_no, use_serial_batch_fields=1)
		return values

	def stock(key, entry_type, day, time, rows, livestock=True):
		remarks = f"{PREFIX}:{setup.batch}:{key}"
		tags = {"lvm_batch": setup.batch, "lvm_livestock_house": setup.house} if livestock else {}
		ensure(
			"Stock Entry",
			{"remarks": remarks, "company": setup.company, "docstatus": ["<", 2]},
			{
				"stock_entry_type": entry_type,
				"company": setup.company,
				"posting_date": day,
				"posting_time": time,
				"set_posting_time": 1,
				"remarks": remarks,
				**tags,
				"items": rows,
			},
			submit=True,
		)

	first = setup.days[0].date
	stock(
		"feed-receipt",
		"Material Receipt",
		first,
		FEED_RECEIPT,
		[row(setup.feed_item, setup.feed_stock_kg, "Kg", target=setup.feed_store, rate=FEED_RATE)],
		livestock=False,
	)
	stock(
		"placement",
		"Material Receipt",
		first,
		PLACEMENT,
		[row(setup.item, PLACED, "Nos", target=setup.house, rate=BIRD_RATE, batch_no=setup.batch)],
	)
	previous_weight = 0.0
	for day in setup.days:
		if day.weight_kg:
			ensure(
				"Weight Record",
				{"batch": setup.batch, "posting_date": f"{day.date} {WEIGH}"},
				{
					"posting_date": f"{day.date} {WEIGH}",
					"recorded_by": setup.employee,
					"item": setup.item,
					"batch": setup.batch,
					"sample_size": SAMPLE_SIZE,
					"population_size": day.population,
					"actual_weight": day.weight_kg,
					"previous_weight": previous_weight,
					"lvm_weight_uom": "Kg",
					"lvm_company": setup.company,
					"lvm_livestock_house": setup.house,
				},
			)
			previous_weight = day.weight_kg
		stock(
			f"feeding-{day.age}",
			"Feeding",
			day.date,
			FEED,
			[row(setup.feed_item, day.feed_kg, "Kg", source=setup.feed_store)],
		)
		if day.deaths:
			stock(
				f"mortality-{day.age}",
				"Mortality",
				day.date,
				DEATHS,
				[row(setup.item, day.deaths, "Nos", source=setup.house, batch_no=setup.batch)],
			)


def verify(setup):
	from livestock_management.livestock_management.report.livestock_batch_performance_report.livestock_batch_performance_report import (
		execute,
	)

	filters = {
		"company": setup.company,
		"from_date": setup.hatch,
		"to_date": setup.end,
		"batch": setup.batch,
		"age_unit": "Weeks",
	}
	_columns, rows = execute(filters)
	row = next((r for r in rows if r.get("batch") == setup.batch and not r.get("is_group")), None)
	keys = (
		"age_weeks",
		"live_qty",
		"mortality_qty",
		"target_mortality_qty",
		"mortality_variance",
		"actual_weight",
		"target_weight_kg",
		"feed_kg",
		"target_feed_kg",
		"fcr",
		"target_fcr",
		"notes",
	)
	result = {key: row.get(key) for key in keys} if row else {}
	missing = [key for key in keys[:-1] if result.get(key) is None]
	if missing:
		frappe.throw(
			_("Demo verification failed: {0} missing. Report notes: {1}").format(
				", ".join(missing), result.get("notes")
			)
		)
	return result
