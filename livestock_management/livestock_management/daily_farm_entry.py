# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

"""Create one farm activity per request; stock review/submission stays in standard forms."""

import hashlib
import json
from uuid import UUID

import frappe
from erpnext.stock.doctype.batch.batch import get_batch_qty
from frappe import _
from frappe.utils import cint, date_diff, flt, get_datetime, now_datetime

ACTIVITIES = {
	"feeding": "Stock Entry",
	"mortality": "Stock Entry",
	"produce": "Stock Entry",
	"weighing": "Weight Record",
	"observation": "Livestock Event",
}
CONTEXT_FIELDS = {"company", "item", "batch", "house", "posting_datetime", "employee", "shift", "project"}
INPUT_FIELDS = {
	"feeding": {"items"},
	"produce": {"items"},
	"mortality": {"quantity", "reason"},
	"weighing": {"sample_size", "average_weight"},
	"observation": {"husbandry", "notes", "ends_on"},
}
ITEM_FIELDS = {"item", "quantity", "warehouse", "batch", "rate"}


def checked_doc(doctype, name):
	if not name:
		frappe.throw(_("{0} is required.").format(_(doctype)))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return doc


def validate_keys(value, allowed):
	if not isinstance(value, dict) or set(value) - allowed:
		frappe.throw(_("Invalid farm entry fields."))


def validate_context(context):
	validate_keys(context, CONTEXT_FIELDS)
	checked_doc("Company", context.get("company"))
	item = checked_doc("Item", context.get("item"))
	batch = checked_doc("Batch", context.get("batch"))
	if not item.is_stock_item or not item.has_batch_no or item.has_serial_no or item.disabled:
		frappe.throw(
			_("This screen currently supports enabled, batch-tracked livestock without serial numbers.")
		)
	if batch.item != item.name or batch.disabled:
		frappe.throw(_("Select an enabled Batch belonging to the livestock Item."))
	validate_warehouse(context.get("house"), context["company"])
	employee = checked_doc("Employee", context.get("employee"))
	if employee.company != context["company"] or employee.status != "Active":
		frappe.throw(_("Select an active Employee in this Company."))
	if context.get("project"):
		project = checked_doc("Project", context["project"])
		if project.company != context["company"]:
			frappe.throw(_("Project must belong to the selected Company."))
	if context.get("shift"):
		checked_doc("Shift Type", context["shift"])
	if not context.get("posting_datetime"):
		frappe.throw(_("Activity date and time are required."))
	timestamp = get_datetime(context["posting_datetime"])
	if timestamp > now_datetime():
		frappe.throw(_("Activity time cannot be in the future."))
	if batch.manufacturing_date and timestamp.date() < get_datetime(batch.manufacturing_date).date():
		frappe.throw(_("Activity time cannot precede the Batch manufacturing date."))
	if population(context, timestamp) <= 0:
		frappe.throw(_("This Batch has no available livestock in the selected house at the activity time."))
	return item, batch, timestamp


def validate_warehouse(name, company):
	warehouse = checked_doc("Warehouse", name)
	if warehouse.company != company or warehouse.is_group or warehouse.disabled:
		frappe.throw(_("Select an enabled non-group Warehouse in this Company."))
	return warehouse


def positive(value):
	quantity = flt(value)
	# Reject NaN and infinity as well as zero/negative quantities.
	if not 0 < quantity < float("inf"):
		frappe.throw(_("Quantities and weights must be positive finite numbers."))
	return quantity


def request_hash(payload):
	return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def result(doc):
	doc.check_permission("read")
	workflow = frappe.get_cached_value(
		"Workflow", {"document_type": doc.doctype, "is_active": 1}, "workflow_state_field"
	)
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"docstatus": doc.docstatus,
		"modified": str(doc.modified),
		"status": doc.get(workflow)
		if workflow
		else (doc.get("status") if doc.doctype != "Stock Entry" else None),
	}


def existing_operation(doctype, operation_id, fingerprint):
	name = frappe.db.get_value(doctype, {"lvm_farm_entry_id": operation_id}, "name")
	if name:
		doc = checked_doc(doctype, name)
		if doc.lvm_farm_entry_hash != fingerprint:
			frappe.throw(
				_(
					"This operation has already been saved with different inputs. Open its document to edit it."
				)
			)
		return result(doc)


@frappe.whitelist(methods=["POST"])
def save_activity(payload):
	"""Create, never submit. Each call is an independent Frappe request transaction."""
	payload = frappe.parse_json(payload) if isinstance(payload, str) else payload
	validate_keys(payload, {"activity", "operation_id", "context", "values"})
	activity = payload.get("activity")
	if activity not in ACTIVITIES:
		frappe.throw(_("Unsupported farm activity."))
	try:
		operation_id = str(UUID(str(payload.get("operation_id"))))
	except (ValueError, TypeError, AttributeError):
		frappe.throw(_("A valid operation ID is required."))
	doctype = ACTIVITIES[activity]
	validate_keys(payload.get("values"), INPUT_FIELDS[activity])
	validate_keys(payload.get("context"), CONTEXT_FIELDS)
	if not frappe.get_meta(doctype).has_field("lvm_farm_entry_id"):
		frappe.throw(_("Run the site migration to install Daily Farm Entry fields."))
	fingerprint = request_hash(payload)
	# A lost response can be recovered even when stock/context has changed since creation.
	existing = existing_operation(doctype, operation_id, fingerprint)
	if existing:
		return existing
	frappe.has_permission(doctype, "create", throw=True)
	item, batch, timestamp = validate_context(payload["context"])
	doc = make_document(activity, payload["context"], payload["values"], item, batch, timestamp)
	doc.lvm_farm_entry_id = operation_id
	doc.lvm_farm_entry_hash = fingerprint
	frappe.db.savepoint("farm_activity_insert")
	try:
		doc.insert()
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback(save_point="farm_activity_insert")
		existing = existing_operation(doctype, operation_id, fingerprint)
		if existing:
			return existing
		raise
	return result(doc)


def population(context, timestamp):
	return flt(
		get_batch_qty(
			batch_no=context["batch"],
			warehouse=context["house"],
			item_code=context["item"],
			posting_date=timestamp.date(),
			posting_time=timestamp.time(),
		)
	)


def make_document(activity, context, values, item, batch, timestamp):
	doc = frappe.new_doc(ACTIVITIES[activity])
	doc.lvm_livestock_house = context["house"]
	if doc.doctype == "Stock Entry":
		doc.update(
			{
				"company": context["company"],
				"lvm_batch": batch.name,
				"lvm_employee": context["employee"],
				"lvm_shift_type": context.get("shift"),
				"project": context.get("project"),
				"set_posting_time": 1,
				"posting_date": timestamp.date(),
				"posting_time": timestamp.time(),
			}
		)
		entry_type, purpose = {
			"feeding": ("Feeding", "Material Issue"),
			"mortality": ("Mortality", "Material Issue"),
			"produce": ("Produce Collection", "Material Receipt"),
		}[activity]
		stock_type = checked_doc("Stock Entry Type", entry_type)
		if stock_type.purpose != purpose:
			frappe.throw(_("The configured Stock Entry Type has an unexpected purpose."))
		doc.stock_entry_type, doc.purpose = entry_type, purpose
		if activity == "mortality":
			checked_doc("Mortality Reason", values.get("reason"))
			qty = positive(values.get("quantity"))
			if qty != int(qty) or qty > population(context, timestamp):
				frappe.throw(
					_("Mortality must be a whole count not exceeding the house's available population.")
				)
			doc.lvm_mortality_reason = values["reason"]
			doc.append(
				"items",
				{
					"item_code": item.name,
					"qty": qty,
					"uom": item.stock_uom,
					"stock_uom": item.stock_uom,
					"conversion_factor": 1,
					"s_warehouse": context["house"],
					"batch_no": batch.name,
					"use_serial_batch_fields": 1,
				},
			)
		else:
			add_stock_rows(doc, activity, values.get("items"), context)
		return doc
	if activity == "weighing":
		checked_doc("UOM", "Kg")
		sample = positive(values.get("sample_size"))
		qty = population(context, timestamp)
		if sample != int(sample) or sample > qty:
			frappe.throw(
				_("Sample size must be a whole count not exceeding the house's available population.")
			)
		# Only compare measurements with explicit, compatible units and location.
		previous = frappe.get_list(
			"Weight Record",
			filters={
				"batch": batch.name,
				"item": item.name,
				"lvm_company": context["company"],
				"lvm_livestock_house": context["house"],
				"lvm_weight_uom": "Kg",
				"posting_date": ["<", timestamp],
				"docstatus": ["<", 2],
			},
			fields=["actual_weight"],
			order_by="posting_date desc, creation desc",
			limit_page_length=1,
		)
		doc.update(
			{
				"batch": batch.name,
				"item": item.name,
				"recorded_by": context["employee"],
				"posting_date": timestamp,
				"sample_size": cint(sample),
				"population_size": cint(qty),
				"actual_weight": positive(values.get("average_weight")),
				"previous_weight": previous[0].actual_weight if previous else 0,
				"age": date_diff(timestamp.date(), batch.manufacturing_date)
				if batch.manufacturing_date
				else None,
				"lvm_weight_uom": "Kg",
			}
		)
	else:
		husbandry = checked_doc("Husbandry Practice", values.get("husbandry"))
		if husbandry.name == "Pregnancy Check":
			frappe.throw(_("Use the standard Livestock Event form for structured pregnancy checks."))
		end = get_datetime(values.get("ends_on") or timestamp)
		if end < timestamp:
			frappe.throw(_("Observation end cannot be before its start."))
		doc.update(
			{
				"animal": item.name,
				"batch": batch.name,
				"performed_by": context["employee"],
				"husbandry": husbandry.name,
				"starts_on": timestamp,
				"ends_on": end,
				"notes": values.get("notes"),
				"status": "Open",
			}
		)
	doc.lvm_company = context["company"]
	doc.lvm_project = context.get("project")
	return doc


def add_stock_rows(doc, activity, rows, context):
	if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
		frappe.throw(_("Enter between 1 and 100 stock rows."))
	for row in rows:
		validate_keys(row, ITEM_FIELDS)
		item = checked_doc("Item", row.get("item"))
		if not item.is_stock_item or item.disabled or item.has_serial_no:
			frappe.throw(
				_(
					"Select an enabled non-serialized stock Item. Use the standard form for serial-tracked items."
				)
			)
		if item.name == context["item"]:
			frappe.throw(_("Feed/produce Item must differ from the livestock Item."))
		validate_warehouse(row.get("warehouse"), context["company"])
		if item.has_batch_no and not row.get("batch"):
			frappe.throw(_("Select the inventory Batch for {0}.").format(item.name))
		if row.get("batch"):
			batch = checked_doc("Batch", row["batch"])
			if not item.has_batch_no or batch.item != item.name or batch.disabled:
				frappe.throw(_("Inventory Batch does not match the selected stock Item."))
		fields = {
			"item_code": item.name,
			"qty": positive(row.get("quantity")),
			"uom": item.stock_uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": 1,
			"batch_no": row.get("batch"),
			"use_serial_batch_fields": 1,
			"s_warehouse" if activity == "feeding" else "t_warehouse": row["warehouse"],
		}
		if activity == "produce":
			fields["basic_rate"] = positive(row.get("rate"))
			fields["set_basic_rate_manually"] = 1
		doc.append("items", fields)


@frappe.whitelist()
def get_recent_activities(company, batch):
	"""Small, bounded history. No cross-document query bypasses source permissions."""
	checked_doc("Company", company)
	checked_doc("Batch", batch)
	rows = []
	for doctype in ("Stock Entry", "Weight Record", "Livestock Event"):
		if not frappe.has_permission(doctype, "read"):
			continue
		meta = frappe.get_meta(doctype)
		if not meta.has_field("lvm_farm_entry_id"):
			continue
		filters = {
			"lvm_farm_entry_id": ["is", "set"],
			"lvm_batch" if doctype == "Stock Entry" else "batch": batch,
			"company" if doctype == "Stock Entry" else "lvm_company": company,
		}
		for row in frappe.get_list(
			doctype,
			filters=filters,
			fields=["name", "modified", "docstatus"],
			order_by="modified desc",
			limit_page_length=10,
		):
			rows.append(result(checked_doc(doctype, row.name)))
	return sorted(rows, key=lambda row: row["modified"], reverse=True)[:20]
