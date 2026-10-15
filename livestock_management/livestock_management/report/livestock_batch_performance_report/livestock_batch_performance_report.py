# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, get_datetime, getdate

PRODUCE_TYPES = {"Produce Collection", "Production", "Egg Production"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for field in ("company", "item_code", "from_date", "to_date"):
		if not filters.get(field):
			frappe.throw(_("Company, Livestock Item, From Date and To Date are required."))
	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be after To Date."))
	for doctype, name in (("Company", filters.company), ("Item", filters.item_code)):
		frappe.get_doc(doctype, name).check_permission("read")
	if filters.batch:
		batch_doc = frappe.get_doc("Batch", filters.batch)
		batch_doc.check_permission("read")
		if batch_doc.item != filters.item_code:
			frappe.throw(_("Batch must belong to the selected Livestock Item."))
	if filters.warehouse:
		warehouse = frappe.get_doc("Warehouse", filters.warehouse)
		warehouse.check_permission("read")
		if warehouse.company != filters.company or warehouse.is_group:
			frappe.throw(_("Select a non-group Warehouse belonging to the selected Company."))
	for doctype in ("Stock Ledger Entry", "Stock Entry"):
		frappe.has_permission(doctype, "read", throw=True)
	item = frappe.get_doc("Item", filters.item_code)
	if not item.has_batch_no or not item.is_stock_item:
		frappe.throw(_("Select a batch-tracked livestock stock Item."))
	return get_columns(), get_data(filters, item)


def get_columns():
	specs = [
		("batch", "Batch", "Link", "Batch"),
		("item_code", "Livestock Item", "Link", "Item"),
		("stock_uom", "Population UOM", "Link", "UOM"),
		("age_days", "Age at End Date (Days)", "Int", None),
		("opening_qty", "Opening Population", "Float", None),
		("incoming_qty", "Incoming Quantity", "Float", None),
		("outgoing_qty", "Outgoing Quantity", "Float", None),
		("live_qty", "Closing Population", "Float", None),
		("mortality_qty", "Period Mortality", "Float", None),
		("survival_percent", "Period Survival (%)", "Percent", None),
		("weight_record", "Latest Weight Record", "Link", "Weight Record"),
		("weight_date", "Latest Weight Date", "Datetime", None),
		("sample_size", "Sample Size", "Int", None),
		("actual_weight", "Latest Recorded Weight", "Float", None),
		("weight_gain", "Recorded Weight Gain", "Float", None),
		("feed_kg", "Period Feed (Kg)", "Float", None),
		("produce_qty", "Period Produce", "Float", None),
		("produce_uom", "Produce UOM", "Link", "UOM"),
		("fcr", "Interval FCR", "Float", None),
		("notes", "Data Notes", "Data", None),
	]
	return [
		{
			"fieldname": name,
			"label": _(label),
			"fieldtype": kind,
			"options": options,
			"width": 300 if name == "notes" else 150,
		}
		for name, label, kind, options in specs
	]


def get_data(filters, item):
	batch_filters = {"item": filters.item_code}
	if filters.batch:
		batch_filters["name"] = filters.batch
	batches = frappe.get_list(
		"Batch",
		filters=batch_filters,
		fields=["name", "manufacturing_date"],
		limit_page_length=0,
	)
	if not batches:
		return []
	batch_names = [b.name for b in batches]
	# Permission-filtered ledger rows; bundle children are read only for these rows.
	ledger_filters = {
		"company": filters.company,
		"item_code": filters.item_code,
		"posting_date": ["<=", filters.to_date],
		"is_cancelled": 0,
		"docstatus": ["<", 2],
	}
	if filters.warehouse:
		ledger_filters["warehouse"] = filters.warehouse
	ledger = frappe.get_list(
		"Stock Ledger Entry",
		filters=ledger_filters,
		fields=[
			"name",
			"posting_date",
			"posting_time",
			"actual_qty",
			"batch_no",
			"serial_and_batch_bundle",
			"voucher_type",
			"voucher_no",
			"warehouse",
		],
		limit_page_length=0,
	)
	bundles = {d.serial_and_batch_bundle for d in ledger if d.serial_and_batch_bundle}
	bundle_rows = defaultdict(list)
	if bundles:
		for d in frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": ["in", list(bundles)]},
			fields=["parent", "batch_no", "qty"],
			limit_page_length=0,
		):
			bundle_rows[d.parent].append(d)
	movements = defaultdict(list)
	for d in ledger:
		# Bundle quantities already carry the inward/outward sign. Do not also count legacy fields.
		parts = (
			bundle_rows[d.serial_and_batch_bundle]
			if d.serial_and_batch_bundle
			else [frappe._dict(batch_no=d.batch_no, qty=d.actual_qty)]
		)
		for part in parts:
			if part.batch_no in batch_names:
				movements[part.batch_no].append(
					frappe._dict(
						date=getdate(d.posting_date),
						timestamp=get_datetime(f"{d.posting_date} {d.posting_time}"),
						qty=flt(part.qty),
						voucher_type=d.voucher_type,
						voucher_no=d.voucher_no,
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
			"posting_date",
			"posting_time",
		],
		limit_page_length=0,
	)
	entry_map = {d.name: d for d in entries}
	# Only load transaction children of readable parents.
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
			fields=[
				"parent",
				"item_code",
				"stock_qty",
				"stock_uom",
				"s_warehouse",
				"t_warehouse",
			],
			limit_page_length=0,
		):
			details[d.parent].append(d)
	weights = defaultdict(list)
	if frappe.has_permission("Weight Record", "read"):
		for d in frappe.get_list(
			"Weight Record",
			filters={
				"batch": ["in", batch_names],
				"item": filters.item_code,
				"docstatus": ["<", 2],
				"posting_date": ["<", add_days(filters.to_date, 1)],
			},
			fields=["name", "batch", "posting_date", "actual_weight", "sample_size"],
			order_by="posting_date asc, creation asc, name asc",
			limit_page_length=0,
		):
			weights[d.batch].append(d)
	rows = []
	for batch in batches:
		moves = movements[batch.name]
		if not moves:
			continue
		rows.append(
			build_row(
				batch,
				item,
				moves,
				weights[batch.name],
				operations,
				details,
				entry_map,
				filters,
			)
		)
	return sorted(rows, key=lambda row: row["batch"])


def build_row(batch, item, moves, weights, operations, details, entry_map, filters):
	period = [m for m in moves if m.date >= filters.from_date]
	# Net each voucher, so a valuation-only Repack does not inflate receipts/issues.
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
	row = dict(
		batch=batch.name,
		item_code=item.name,
		stock_uom=item.stock_uom,
		age_days=(date_diff(filters.to_date, batch.manufacturing_date) if batch.manufacturing_date else None),
		opening_qty=opening,
		incoming_qty=incoming,
		outgoing_qty=outgoing,
		live_qty=opening + incoming - outgoing,
		mortality_qty=mortality,
		survival_percent=None,
		feed_kg=0.0,
		produce_qty=0.0,
		produce_uom=None,
		fcr=None,
	)
	notes = []
	# A period survival rate is defensible only without arrivals, sales, transfers or corrections.
	stable = not incoming and abs(outgoing - mortality) < 0.000001
	if opening > 0 and stable:
		row["survival_percent"] = 100 * (opening - mortality) / opening
	else:
		notes.append(_("Survival unavailable: no opening population or non-mortality movements."))
	if weights:
		latest = weights[-1]
		row.update(
			weight_record=latest.name,
			weight_date=latest.posting_date,
			sample_size=latest.sample_size,
			actual_weight=latest.actual_weight,
		)
		if len(weights) > 1:
			row["weight_gain"] = flt(latest.actual_weight) - flt(weights[-2].actual_weight)
		notes.append(_("Saved batch-wide weights; units/approval are not recorded."))
	else:
		notes.append(_("No readable weight measurement."))
	feed_events = []
	produce = defaultdict(float)
	for entry in operations:
		if entry.lvm_batch != batch.name:
			continue
		for detail in details[entry.name]:
			if (
				entry.stock_entry_type == "Feeding"
				and entry.purpose == "Material Issue"
				and detail.s_warehouse
			):
				kg = to_kg(detail.item_code, detail.stock_uom, detail.stock_qty)
				feed_events.append((get_datetime(f"{entry.posting_date} {entry.posting_time}"), kg))
			elif (
				entry.stock_entry_type in PRODUCE_TYPES
				and entry.purpose == "Material Receipt"
				and detail.t_warehouse
			):
				produce[detail.stock_uom] += flt(detail.stock_qty)
	if any(q is None for _, q in feed_events):
		row["feed_kg"] = None
		notes.append(_("Feed has no valid conversion to Kg."))
	else:
		row["feed_kg"] = sum(q for _, q in feed_events)
	if len(produce) == 1:
		row["produce_uom"], row["produce_qty"] = next(iter(produce.items()))
	elif produce:
		row["produce_qty"] = None
		notes.append(_("Produce uses mixed UOMs; quantities cannot be summed."))
	if filters.warehouse:
		row.update(feed_kg=None, produce_qty=None, produce_uom=None)
		notes.append(_("House-specific feed/produce allocation is not recorded."))
	elif filters.weights_are_kg and item.stock_uom == "Nos" and len(weights) >= 2:
		start, end = weights[-2:]
		start_time, end_time = get_datetime(start.posting_date), get_datetime(end.posting_date)
		gain = flt(end.actual_weight) - flt(start.actual_weight)
		interval = [m for m in moves if start_time < m.timestamp <= end_time]
		interval_feed = [q for t, q in feed_events if start_time < t <= end_time]
		population = sum(m.qty for m in moves if m.timestamp <= start_time)
		if (
			start_time.date() >= filters.from_date
			and end_time > start_time
			and gain > 0
			and population > 0
			and not interval
			and interval_feed
			and all(q is not None for q in interval_feed)
		):
			row["fcr"] = sum(interval_feed) / (population * gain)
	if row["fcr"] is None:
		notes.append(
			_("FCR needs confirmed kg/animal weights, Nos population, interval feed and no stock movements.")
		)
	notes.append(_("Age targets and hen-day yield are not configured."))
	row["notes"] = " ".join(notes)  # type: ignore
	return row


def to_kg(item_code, stock_uom, qty):
	if stock_uom == "Kg":
		return flt(qty)
	# An Item conversion factor specifies stock units per alternate UOM.
	conversion = frappe.db.get_value(
		"UOM Conversion Detail", {"parent": item_code, "uom": "Kg"}, "conversion_factor"
	)
	return flt(qty) / flt(conversion) if flt(conversion) > 0 else None
