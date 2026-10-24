# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from collections import defaultdict
from math import isfinite

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, get_datetime, getdate

from livestock_management.livestock_management.batch_stock import get_batch_movements
from livestock_management.livestock_management.dashboard_chart_source.daily_population.daily_population import (
	daily_balances,
)
from livestock_management.livestock_management.number_card.feed_consumed.feed_consumed import sum_feed_kg
from livestock_management.livestock_management.performance_fcr import calculate_fcr
from livestock_management.livestock_management.performance_targets import age_on, apply_targets
from livestock_management.livestock_management.stock_units import to_kg

PRODUCE_TYPES = {"Produce Collection", "Production", "Egg Production"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for field in ("company", "from_date", "to_date"):
		if not filters.get(field):
			frappe.throw(_("Company, From Date and To Date are required."))
	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be after To Date."))
	frappe.get_doc("Company", filters.company).check_permission("read")
	if filters.batch:
		batch_doc = frappe.get_doc("Batch", filters.batch)
		batch_doc.check_permission("read")
		if filters.item_code and batch_doc.item != filters.item_code:
			frappe.throw(_("Batch must belong to the selected Livestock Item."))
		filters.item_code = batch_doc.item
	if filters.warehouse:
		warehouse = frappe.get_doc("Warehouse", filters.warehouse)
		warehouse.check_permission("read")
		if warehouse.company != filters.company or warehouse.is_group:
			frappe.throw(_("Select a non-group Warehouse belonging to the selected Company."))
	for doctype in ("Stock Ledger Entry", "Stock Entry"):
		frappe.has_permission(doctype, "read", throw=True)
	if filters.item_code:
		item = frappe.get_doc("Item", filters.item_code)
		item.check_permission("read")
		if not item.has_batch_no or not item.is_stock_item:
			frappe.throw(_("Select a batch-tracked livestock stock Item."))
		items = [item]
	else:
		items = frappe.get_list(
			"Item",
			filters={"has_batch_no": 1, "is_stock_item": 1},
			fields=["name", "stock_uom"],
			order_by="name asc",
			limit_page_length=0,
		)
	return get_columns(), group_by_item(get_data(filters, items))


def group_by_item(rows):
	"""Item headings carry no totals: ratios and produce UOMs are batch-specific."""
	result = []
	for row in sorted(rows, key=lambda row: (row["item_code"], row["batch"])):
		parent = f"item:{row['item_code']}"
		if not result or result[-1]["parent_row_id"] != parent:
			result.append(
				{
					"row_id": parent,
					"parent_row_id": None,
					"entity_name": row["item_code"],
					"entity_doctype": "Item",
					"item_code": row["item_code"],
					"indent": 0,
					"is_group": 1,
				}
			)
		result.append(
			{
				**row,
				"row_id": f"batch:{row['batch']}",
				"parent_row_id": parent,
				"entity_name": row["batch"],
				"entity_doctype": "Batch",
				"indent": 1,
				"is_group": 0,
			}
		)
	return result


def get_columns():
	specs = [
		("entity_name", "Livestock Item / Batch", "Dynamic Link", "entity_doctype"),
		("batch", "Batch", "Link", "Batch"),
		("item_code", "Livestock Item", "Link", "Item"),
		("stock_uom", "Population UOM", "Link", "UOM"),
		("age_days", "Age at End Date (Days)", "Int", None),
		("performance_profile", "Performance Profile", "Link", "Livestock Performance Profile"),
		("opening_qty", "Opening Population", "Float", None),
		("incoming_qty", "Incoming Quantity", "Float", None),
		("outgoing_qty", "Outgoing Quantity", "Float", None),
		("live_qty", "Closing Population", "Float", None),
		("mortality_qty", "Period Mortality", "Float", None),
		("survival_percent", "Period Survival (%)", "Percent", None),
		("weight_record", "Latest Weight Record", "Link", "Weight Record"),
		("weight_date", "Latest Weight Date", "Datetime", None),
		("sample_size", "Sample Size", "Int", None),
		("actual_weight", "Latest Average Weight (kg/animal)", "Float", None),
		("weight_gain", "Recorded Weight Gain", "Float", None),
		("feed_kg", "Period Feed (Kg)", "Float", None),
		("produce_qty", "Period Produce", "Float", None),
		("produce_uom", "Produce UOM", "Link", "UOM"),
		("fcr", "Interval FCR", "Float", None),
		("weight_age_days", "Weight Measurement Age (Days)", "Int", None),
		("target_weight_kg", "Target Weight (kg/animal)", "Float", None),
		("weight_variance", "Weight Variance (kg/animal)", "Float", None),
		("weight_variance_percent", "Weight Variance (%)", "Percent", None),
		("target_feed_kg", "Target Period Feed (kg)", "Float", None),
		("feed_variance", "Feed Variance (kg)", "Float", None),
		("feed_variance_percent", "Feed Variance (%)", "Percent", None),
		("fcr_from_date", "FCR Interval Start", "Datetime", None),
		("fcr_to_date", "FCR Interval End", "Datetime", None),
		("target_fcr", "Target Interval FCR", "Float", None),
		("fcr_variance", "FCR Variance (kg/kg)", "Float", None),
		("fcr_variance_percent", "FCR Variance (%)", "Percent", None),
		("egg_count", "Eggs Laid (All Categories)", "Float", None),
		("hen_day_yield", "Hen-Day Yield (%)", "Percent", None),
		("target_hen_day_yield", "Target Hen-Day Yield (%)", "Percent", None),
		("egg_yield_variance_pp", "Egg Yield Variance (pp)", "Float", None),
		("notes", "Data Notes", "Data", None),
	]
	return [
		{
			"fieldname": name,
			"label": _(label),
			"fieldtype": kind,
			"options": options,
			"width": 300 if name in {"entity_name", "notes"} else 150,
		}
		for name, label, kind, options in specs
	]


def get_data(filters, items):
	# Accept one Item as well as a list for existing internal callers.
	items = items if isinstance(items, list) else [items]
	item_map = {item.name: item for item in items}
	if not item_map:
		return []
	filters = frappe._dict(filters)
	filters.item_codes = list(item_map)
	batch_filters = {"item": ["in", list(item_map)]}
	if filters.batch:
		batch_filters["name"] = filters.batch
	batches = frappe.get_list(
		"Batch",
		filters=batch_filters,
		fields=["name", "item", "lvm_hatch_date", "lvm_performance_profile"],
		limit_page_length=0,
	)
	if not batches:
		return []
	batch_names = [b.name for b in batches]
	movements = get_batch_movements(filters, batch_names)
	warehouses = set(
		frappe.get_list(
			"Warehouse",
			filters={"company": filters.company, "is_group": 0},
			pluck="name",
			limit_page_length=0,
		)
	)
	entries = frappe.get_list(
		"Stock Entry",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name",
			"purpose",
			"stock_entry_type",
			"lvm_batch",
			"lvm_livestock_house",
			"posting_date",
			"posting_time",
		],
		limit_page_length=0,
	)
	entry_map = {d.name: d for d in entries}
	operations = [
		d
		for d in entries
		if d.lvm_batch in batch_names
		and filters.from_date <= getdate(d.posting_date) <= filters.to_date
		and (d.stock_entry_type == "Feeding" or d.stock_entry_type in PRODUCE_TYPES)
	]
	details = defaultdict(list)
	if operations:
		for d in frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": ["in", [e.name for e in operations]]},
			fields=["parent", "item_code", "transfer_qty", "stock_uom", "s_warehouse", "t_warehouse"],
			limit_page_length=0,
		):
			details[d.parent].append(d)
	readable_items = (
		set(
			frappe.get_list(
				"Item",
				filters={"name": ["in", list({d.item_code for rows in details.values() for d in rows})]},
				pluck="name",
				limit_page_length=0,
			)
		)
		if details
		else set()
	)
	# Mark inaccessible child data; do not silently sum a readable subset.
	for entry in operations:
		entry.inaccessible_details = any(
			d.item_code not in readable_items
			or (d.s_warehouse and d.s_warehouse not in warehouses)
			or (d.t_warehouse and d.t_warehouse not in warehouses)
			for d in details[entry.name]
		)
		entry.inaccessible_house = entry.lvm_livestock_house not in warehouses
	weights = defaultdict(list)
	weight_access = frappe.has_permission("Weight Record", "read")
	if weight_access:
		for d in frappe.get_list(
			"Weight Record",
			filters={
				"batch": ["in", batch_names],
				"item": ["in", list(item_map)],
				"lvm_company": filters.company,
				"docstatus": ["<", 2],
				"posting_date": ["<", add_days(filters.to_date, 1)],
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
		):
			d.inaccessible_house = d.lvm_livestock_house not in warehouses
			weights[d.batch].append(d)
	profile_names = list({b.lvm_performance_profile for b in batches if b.lvm_performance_profile})
	profiles = {}
	if profile_names and frappe.has_permission("Livestock Performance Profile", "read"):
		for name in frappe.get_list(
			"Livestock Performance Profile",
			filters={"name": ["in", profile_names], "docstatus": 1},
			pluck="name",
			limit_page_length=0,
		):
			profile = frappe.get_doc("Livestock Performance Profile", name)
			profile.check_permission("read")
			profiles[name] = profile
	rows = []
	for batch in batches:
		moves = movements.get(batch.name, [])
		if not moves:
			continue
		row = build_row(
			batch,
			item_map[batch.item],
			moves,
			weights[batch.name],
			operations,
			details,
			entry_map,
			filters,
			profiles.get(batch.lvm_performance_profile),
		)
		if not weight_access:
			row["notes"] += " No permission to read weight measurements."
		rows.append(row)
	return sorted(rows, key=lambda row: row["batch"])


def build_row(batch, item, moves, weights, operations, details, entry_map, filters, profile=None):
	period = [m for m in moves if filters.from_date <= m.date <= filters.to_date]
	net = defaultdict(float)
	for m in period:
		net[(m.voucher_type, m.voucher_no)] += m.qty
	opening = sum(m.qty for m in moves if m.date < filters.from_date)
	incoming = sum(q for q in net.values() if q > 0)
	outgoing = -sum(q for q in net.values() if q < 0)
	mortality = -sum(
		m.qty
		for m in period
		if m.qty < 0
		and m.voucher_type == "Stock Entry"
		and m.voucher_no in entry_map
		and entry_map[m.voucher_no].stock_entry_type == "Mortality"
	)
	row = {column["fieldname"]: None for column in get_columns()}
	row.update(
		batch=batch.name,
		item_code=item.name,
		stock_uom=item.stock_uom,
		performance_profile=profile.name if profile else None,
		age_days=age_on(filters.to_date, batch.get("lvm_hatch_date")),
		opening_qty=opening,
		incoming_qty=incoming,
		outgoing_qty=outgoing,
		live_qty=opening + incoming - outgoing,
		mortality_qty=mortality,
	)
	notes = []
	if opening > 0 and not incoming and abs(outgoing - mortality) < 0.000001:
		row["survival_percent"] = 100 * (opening - mortality) / opening
	else:
		notes.append("Survival unavailable: no opening population or non-mortality movements.")
	if not batch.get("lvm_hatch_date"):
		notes.append("Biological age unavailable: Hatch/Birth Date is missing.")
	weights = [w for w in weights if getdate(w.posting_date) <= filters.to_date]
	invalid_house = any(not w.lvm_livestock_house or w.get("inaccessible_house") for w in weights)
	if filters.warehouse:
		weights = [w for w in weights if w.lvm_livestock_house == filters.warehouse]
	valid_weights = []
	for weight in weights:
		population = sum(
			m.qty
			for m in moves
			if m.get("warehouse") == weight.lvm_livestock_house
			and m.timestamp <= get_datetime(weight.posting_date)
		)
		if (
			weight.lvm_weight_uom == "Kg"
			and isfinite(flt(weight.actual_weight))
			and flt(weight.actual_weight) > 0
			and 0 < flt(weight.sample_size) <= population
		):
			valid_weights.append(weight)
	# A single house's latest sample must not stand in for an entire multi-house batch.
	weight_houses = defaultdict(float)
	if valid_weights:
		last_time = max(get_datetime(w.posting_date) for w in valid_weights)
		for movement in moves:
			if movement.timestamp <= last_time:
				weight_houses[movement.get("warehouse")] += movement.qty
	if (
		not invalid_house
		and len({w.lvm_livestock_house for w in valid_weights}) == 1
		and len([q for q in weight_houses.values() if q > 0]) == 1
	):
		latest = sorted(valid_weights, key=lambda w: (get_datetime(w.posting_date), w.name))[-1]
		row.update(
			weight_record=latest.name,
			weight_date=latest.posting_date,
			sample_size=latest.sample_size,
			actual_weight=flt(latest.actual_weight),
			weight_age_days=age_on(latest.posting_date, batch.get("lvm_hatch_date")),
		)
		ordered = sorted(valid_weights, key=lambda w: (get_datetime(w.posting_date), w.name))
		if len(ordered) > 1:
			row["weight_gain"] = flt(latest.actual_weight) - flt(ordered[-2].actual_weight)
	else:
		notes.append(
			"Weight unavailable: need valid kg/animal samples in one accessible house; select a House if needed."
		)
	batch_ops = [e for e in operations if e.lvm_batch == batch.name]
	unknown_house = any(not e.lvm_livestock_house or e.get("inaccessible_house") for e in batch_ops)
	if filters.warehouse:
		batch_ops = [e for e in batch_ops if e.lvm_livestock_house == filters.warehouse]
	feeding = [e for e in batch_ops if e.stock_entry_type == "Feeding" and e.purpose == "Material Issue"]
	produce_ops = [
		e for e in batch_ops if e.stock_entry_type in PRODUCE_TYPES and e.purpose == "Material Receipt"
	]
	feed_rows = [d for e in feeding for d in details.get(e.name, [])]
	feed_invalid = unknown_house or any(
		e.get("inaccessible_details") or not details.get(e.name) for e in feeding
	)
	if feed_invalid:
		notes.append("Feed unavailable: incomplete or inaccessible feeding details/house.")
	else:
		row["feed_kg"], reason = sum_feed_kg(feed_rows)
		if reason:
			notes.append(reason)
	produce = defaultdict(float)
	egg_count = 0.0
	egg_items = {e.item for e in profile.egg_items} if profile else set()
	produce_invalid = unknown_house
	for e in produce_ops:
		if e.get("inaccessible_details") or not details.get(e.name):
			produce_invalid = True
		for d in details.get(e.name, []):
			if (
				not d.t_warehouse
				or d.s_warehouse
				or not isfinite(flt(d.transfer_qty))
				or flt(d.transfer_qty) <= 0
			):
				produce_invalid = True
			produce[d.stock_uom] += flt(d.transfer_qty)
			if d.item_code in egg_items:
				if d.stock_uom not in ("Nos", "Unit"):
					produce_invalid = True
				egg_count += flt(d.transfer_qty)
	if produce_invalid:
		egg_count = None
		notes.append(
			"Produce/egg yield unavailable: incomplete quantities, units, or inaccessible house/details."
		)
	elif not produce:
		row["produce_qty"] = 0
	elif len(produce) == 1:
		row["produce_uom"], row["produce_qty"] = next(iter(produce.items()))
	else:
		notes.append("Produce has mixed stock UOMs; generic totals are unavailable.")
	intervals = []
	if item.stock_uom in ("Nos", "Unit") and not invalid_house and not feed_invalid:
		period_weights = [w for w in weights if getdate(w.posting_date) >= filters.from_date]
		row["fcr"], reason, intervals = calculate_fcr(
			{batch.name: moves}, period_weights, feeding, feed_rows, filters.from_date, sum_feed_kg
		)
		if reason:
			notes.append(reason)
	else:
		notes.append(
			"FCR unavailable: count-based population and accessible, explicit house records are required."
		)
	if intervals:
		row["fcr_from_date"] = min(i["from_date"] for i in intervals)
		row["fcr_to_date"] = max(i["to_date"] for i in intervals)
		if len(intervals) > 1:
			notes.append(
				"FCR spans house intervals: "
				+ "; ".join(f"{i['warehouse']}: {i['from_date']} to {i['to_date']}" for i in intervals)
			)
	labels, values = daily_balances({batch.name: moves}, filters.from_date, filters.to_date)
	if item.stock_uom in ("Nos", "Unit"):
		apply_targets(
			row, batch, profile, list(zip(labels, values, strict=True)), intervals, egg_count, notes
		)
	else:
		notes.append("Age target comparisons require population in Nos or Unit.")
	row["notes"] = " ".join(_(note) for note in notes)
	return row
