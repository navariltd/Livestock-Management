# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

"""Read-only batch lifecycle assembled from permission-scoped source documents."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, escape_html, flt, get_datetime, getdate, nowdate

from livestock_management.livestock_management.report.batch_lifecycle_traceability.lineage import (
	reachable_batches,
)
from livestock_management.livestock_management.report.batch_lifecycle_traceability.sources import (
	LifecycleSources,
)

EVENT_TYPES = (
	"Receipt",
	"Birth",
	"Husbandry",
	"Weighing",
	"Treatment",
	"Feeding",
	"Produce collection",
	"Transfer",
	"Split",
	"Merge",
	"Batch replacement",
	"Reclassification / possible grading",
	"Ambiguous transformation",
	"Repack",
	"Mortality",
	"Culling",
	"Sale",
	"Customer return",
	"Supplier return",
	"Capitalisation",
	"Correction",
	"Stock issue",
)


def execute(filters=None):
	filters = validate_filters(filters)
	frappe.has_permission("Stock Ledger Entry", "read", throw=True)
	sources = LifecycleSources(filters)
	if filters.batch not in sources.batches:
		frappe.throw(_("Select an accessible batch-tracked stock Item counted in Nos or Unit."))
	batches = reachable_batches(filters.batch, sources.transformations, filters.include_related_batches)
	activities = sources.activities(batches)
	rows = stock_events(sources, batches, activities)
	rows.extend(linked_stock_events(sources, batches, rows, activities))
	rows.extend(activity_events(sources, activities))
	rows = filter_events(rows, filters)
	message = "<br>".join(escape_html(_(notice)) for notice in sorted(sources.notices))
	return get_columns(), rows, message


def validate_filters(filters):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.batch:
		frappe.throw(_("Company and Batch are required."))
	filters.to_date = getdate(filters.to_date or nowdate())
	filters.from_date = getdate(filters.from_date) if filters.from_date else None
	if filters.to_date > getdate(nowdate()) or (filters.from_date and filters.from_date > filters.to_date):
		frappe.throw(_("Select a historical date range with From Date on or before To Date."))
	filters.include_related_batches = cint(filters.get("include_related_batches", 1))
	if filters.event_type and filters.event_type not in EVENT_TYPES:
		frappe.throw(_("Select a supported lifecycle Event Type."))
	frappe.get_doc("Company", filters.company).check_permission("read")
	batch = frappe.get_doc("Batch", filters.batch)
	batch.check_permission("read")
	item = frappe.get_doc("Item", batch.item)
	item.check_permission("read")
	if not item.is_stock_item or not item.has_batch_no or item.stock_uom not in ("Nos", "Unit"):
		frappe.throw(_("Select a batch-tracked stock Item counted in Nos or Unit."))
	if filters.warehouse:
		warehouse = frappe.get_doc("Warehouse", filters.warehouse)
		warehouse.check_permission("read")
		if warehouse.company != filters.company or warehouse.is_group:
			frappe.throw(_("Select a non-group Warehouse in the selected Company."))
	return filters


def get_columns():
	fields = [
		("timestamp", "Event Time", "Datetime", None),
		("batch", "Batch", "Link", "Batch"),
		("item_code", "Livestock Item", "Link", "Item"),
		("event_type", "Event Type", "Data", None),
		("source_doctype", "Document Type", "Link", "DocType"),
		("source_name", "Source Document", "Dynamic Link", "source_doctype"),
		("status", "Status", "Data", None),
		("source_warehouse", "Source Warehouse", "Link", "Warehouse"),
		("target_warehouse", "Destination Warehouse", "Link", "Warehouse"),
		("activity_warehouse", "Activity Warehouse", "Link", "Warehouse"),
		("qty_in", "Animals In", "Float", None),
		("qty_out", "Animals Out", "Float", None),
		("stock_uom", "Population UOM", "Link", "UOM"),
		("reference_doctype", "Linked Document Type", "Link", "DocType"),
		("reference_name", "Linked Document", "Dynamic Link", "reference_doctype"),
		("customer", "Customer", "Link", "Customer"),
		("parent_batches", "Parent Batches", "Data", None),
		("child_batches", "Child Batches", "Data", None),
		("related_batches", "Related Batches", "Data", None),
		("evidence", "Relationship Evidence", "Data", None),
		("notes", "Data Notes", "Data", None),
	]
	return [
		dict(
			fieldname=name,
			label=_(label),
			fieldtype=kind,
			options=options,
			width=300 if name == "notes" else 170,
		)
		for name, label, kind, options in fields
	]


def base_event(sources, batch, doctype, name, timestamp, event_type, house=None):
	return dict(
		timestamp=str(get_datetime(timestamp)),
		event_type=event_type,
		batch=batch,
		item_code=sources.batches[batch].item,
		stock_uom=sources.items[sources.batches[batch].item].stock_uom,
		source_doctype=doctype,
		source_name=name,
		status="Submitted",
		source_warehouse=None,
		target_warehouse=None,
		activity_warehouse=house,
		qty_in=None,
		qty_out=None,
		customer=None,
		reference_doctype=None,
		reference_name=None,
		parent_batches="",
		child_batches="",
		related_batches="",
		parent_batch_names=[],
		child_batch_names=[],
		related_batch_names=[],
		evidence="Recorded document",
		notes="",
	)


def stock_event_type(doctype, document, qty_in, qty_out, transformation=None, birth=False):
	if doctype == "Stock Reconciliation":
		return "Correction"
	if doctype in ("Delivery Note", "Sales Invoice"):
		return "Customer return" if document.get("is_return") else "Sale"
	if doctype in ("Purchase Receipt", "Purchase Invoice"):
		return "Supplier return" if document.get("is_return") else "Receipt"
	if doctype == "Stock Entry":
		if document.purpose == "Repack":
			return transformation["event_type"] if transformation else "Ambiguous transformation"
		if document.purpose in (
			"Material Transfer",
			"Material Transfer for Manufacture",
			"Send to Subcontractor",
		):
			return "Transfer"
		if document.stock_entry_type == "Mortality":
			return "Mortality"
		if document.stock_entry_type == "Culling":
			return "Culling"
		if document.purpose == "Material Receipt":
			return "Birth" if birth else "Receipt"
	return "Receipt" if qty_in > 0 and qty_out == 0 else "Stock issue"


def set_references(row, document, sources, activities):
	diagnoses = {d.name for d in activities.get("Veterinary Diagnosis", [])}
	if document.get("lvm_veterinary_diagnosis") in diagnoses:
		row.update(reference_doctype="Veterinary Diagnosis", reference_name=document.lvm_veterinary_diagnosis)
	elif document.get("lvm_offspring_record") in sources.offspring:
		row.update(reference_doctype="Offspring Record", reference_name=document.lvm_offspring_record)
	elif document.get("lvm_source_material_issue") in sources.docs.get("Stock Entry", {}):
		row.update(reference_doctype="Stock Entry", reference_name=document.lvm_source_material_issue)


def stock_events(sources, batches, activities):
	groups = {}
	for batch in sorted(batches):
		for movement in sources.movements.get(batch, []):
			key = (movement.voucher_type, movement.voucher_no, batch, movement.warehouse)
			if key not in groups:
				groups[key] = dict(timestamp=movement.timestamp, qty_in=0.0, qty_out=0.0)
			group = groups[key]
			group["qty_in"] += max(0, flt(movement.qty))
			group["qty_out"] += max(0, -flt(movement.qty))
	rows = []
	for (doctype, name, batch, house), group in groups.items():
		document = sources.docs[doctype][name]
		transformation = sources.transformations.get(name) if doctype == "Stock Entry" else None
		birth = document.get("lvm_offspring_record") in sources.offspring
		event_type = stock_event_type(
			doctype, document, group["qty_in"], group["qty_out"], transformation, birth
		)
		row = base_event(sources, batch, doctype, name, group["timestamp"], event_type)
		row.update(
			qty_in=group["qty_in"],
			qty_out=group["qty_out"],
			source_warehouse=house if group["qty_out"] else None,
			target_warehouse=house if group["qty_in"] else None,
			evidence="Posted stock",
		)
		if document.get("customer") in sources.customers:
			row["customer"] = document.customer
		if transformation:
			for key, names in (("parent", transformation["parents"]), ("child", transformation["children"])):
				row[key + "_batch_names"] = names
				row[key + "_batches"] = ", ".join(names)
			related = sorted(set(transformation["parents"] + transformation["children"]) - {batch})
			if event_type == "Ambiguous transformation":
				# Associations are visible but never treated as lineage edges.
				related = sorted(set(transformation.get("associated_batches", [])) - {batch})
			row.update(
				related_batches=", ".join(related),
				related_batch_names=related,
				evidence=transformation["evidence"],
				notes=transformation["notes"],
			)
		set_references(row, document, sources, activities)
		rows.append(row)
	return rows


def linked_stock_events(sources, batches, existing_rows, activities):
	"""Operational stock issues refer to livestock through the header, not their feed/medicine batches."""
	existing = {(r["source_doctype"], r["source_name"], r["batch"]) for r in existing_rows}
	rows = []
	for document in sources.docs.get("Stock Entry", {}).values():
		batch, house = document.lvm_batch, document.lvm_livestock_house
		if batch not in batches or ("Stock Entry", document.name, batch) in existing:
			continue
		if house not in sources.warehouses:
			sources.notices.add(
				"Header-linked stock activities without an accessible historical warehouse are excluded."
			)
			continue
		if document.stock_entry_type == "Feeding" and document.purpose == "Material Issue":
			type_ = "Feeding"
		elif document.stock_entry_type in ("Medical", "Treatment") and document.purpose == "Material Issue":
			type_ = "Treatment"
		elif (
			document.stock_entry_type in ("Produce Collection", "Production", "Egg Production")
			and document.purpose == "Material Receipt"
		):
			type_ = "Produce collection"
		else:
			continue
		row = base_event(
			sources,
			batch,
			"Stock Entry",
			document.name,
			f"{document.posting_date} {document.posting_time or '00:00:00'}",
			type_,
			house,
		)
		row["notes"] = (
			"Linked operation; feed, medicine and produce quantities are not animal population movements."
		)
		set_references(row, document, sources, activities)
		rows.append(row)
	return rows


def activity_events(sources, activities):
	rows = []
	for doctype, documents in activities.items():
		for document in documents:
			if doctype == "Weight Record":
				date, type_, status = document.posting_date, "Weighing", "Saved"
				notes = f"Recorded average weight: {document.actual_weight} {document.lvm_weight_uom or '(unit missing)'}; sample size: {document.sample_size}."
			elif doctype == "Livestock Event":
				date, type_, status = document.starts_on, "Husbandry", document.status
				notes = f"Husbandry practice: {document.husbandry}."
			else:
				date, type_, status = document.diagnosis_date, "Treatment", document.status
				notes = f"Treatment type: {document.treatment_type or 'Not specified'}."
			row = base_event(
				sources, document.batch, doctype, document.name, date, type_, document.lifecycle_house
			)
			row.update(status=status, notes=notes)
			if doctype == "Veterinary Diagnosis" and document.medical_stock_entry in sources.docs.get(
				"Stock Entry", {}
			):
				row.update(reference_doctype="Stock Entry", reference_name=document.medical_stock_entry)
			rows.append(row)
	return rows


def filter_events(rows, filters):
	def included(row):
		day = getdate(row["timestamp"])
		return (
			day <= filters.to_date
			and (not filters.from_date or day >= filters.from_date)
			and (not filters.event_type or row["event_type"] == filters.event_type)
			and (
				not filters.warehouse
				or filters.warehouse
				in (row.get("source_warehouse"), row.get("target_warehouse"), row.get("activity_warehouse"))
			)
		)

	return sorted(
		(row for row in rows if included(row)),
		key=lambda r: (
			r["timestamp"],
			r["source_doctype"],
			r["source_name"],
			r["batch"],
			r.get("source_warehouse") or r.get("target_warehouse") or r.get("activity_warehouse") or "",
		),
	)
