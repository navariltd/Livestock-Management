# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from math import isfinite

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate, nowdate

from livestock_management.livestock_management.report.livestock_batch_performance_report.livestock_batch_performance_report import (
	to_kg,
)


@frappe.whitelist()
def get(filters: str | dict | list | None = None):
	parsed = frappe.parse_json(filters) if isinstance(filters, str) else filters
	if parsed is None or parsed == []:
		parsed = {}
	if not isinstance(parsed, dict):
		frappe.throw(_("Invalid Feed Consumed filters."))
	scope = dict(parsed)
	scope["company"] = scope.get("company") or frappe.defaults.get_user_default("Company")
	if not scope["company"]:
		frappe.throw(_("Set a default Company or select Company in the card filters."))
	scope["to_date"] = getdate(scope.get("to_date") or nowdate())
	scope["from_date"] = getdate(scope.get("from_date") or get_first_day(scope["to_date"]))
	if scope["from_date"] > scope["to_date"] or scope["to_date"] > getdate(nowdate()):
		frappe.throw(_("Select a historical date range with From Date on or before To Date."))
	frappe.get_doc("Company", scope["company"]).check_permission("read")
	frappe.has_permission("Stock Entry", "read", throw=True)
	if not frappe.get_meta("Batch").has_field("lvm_is_livestock_item"):
		frappe.throw(_("Run migration to install the Batch livestock classification field."))
	if scope.get("item_code"):
		frappe.get_doc("Item", scope["item_code"]).check_permission("read")
	if scope.get("batch"):
		batch = frappe.get_doc("Batch", scope["batch"])
		batch.check_permission("read")
		if not batch.get("lvm_is_livestock_item") or (
			scope.get("item_code") and batch.item != scope["item_code"]
		):
			frappe.throw(_("Select a livestock Batch matching the selected Item."))
	if scope.get("warehouse"):
		house = frappe.get_doc("Warehouse", scope["warehouse"])
		house.check_permission("read")
		if house.company != scope["company"] or house.is_group:
			frappe.throw(_("Select a non-group livestock house in this Company."))
	item_filters = {"is_stock_item": 1, "has_batch_no": 1}
	if scope.get("item_code"):
		item_filters["name"] = scope["item_code"]
	items = frappe.get_list("Item", filters=item_filters, pluck="name", limit_page_length=0)
	batch_filters = {"lvm_is_livestock_item": 1, "item": ["in", items]}
	if scope.get("batch"):
		batch_filters["name"] = scope["batch"]
	batches = (
		frappe.get_list("Batch", filters=batch_filters, pluck="name", limit_page_length=0) if items else []
	)
	scope["batch_names"] = batches
	entries = (
		frappe.get_list(
			"Stock Entry",
			filters={
				"company": scope["company"],
				"docstatus": 1,
				"stock_entry_type": "Feeding",
				"purpose": "Material Issue",
				"lvm_batch": ["in", batches],
				"posting_date": ["between", [scope["from_date"], scope["to_date"]]],
			},
			fields=["name", "lvm_livestock_house"],
			limit_page_length=0,
		)
		if batches
		else []
	)
	if scope.get("warehouse"):
		if any(not e.lvm_livestock_house for e in entries):
			return response(
				None,
				scope,
				"Some feeding entries lack a livestock house; house consumption cannot be allocated reliably.",
			)
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
	if not rows:
		return response(0, scope, None)
	warehouses = frappe.get_list(
		"Warehouse", filters={"company": scope["company"], "is_group": 0}, pluck="name", limit_page_length=0
	)
	feed_items = frappe.get_list(
		"Item", filters={"name": ["in", list({r.item_code for r in rows})]}, pluck="name", limit_page_length=0
	)
	if any(r.s_warehouse not in warehouses or r.item_code not in feed_items for r in rows):
		return response(None, scope, "Not all feeding details are accessible with your current permissions.")
	value, reason = sum_feed_kg(rows)
	return response(value, scope, reason)


def sum_feed_kg(rows):
	"""transfer_qty is already expressed in stock UOM: do not convert the entered qty twice."""
	total = 0.0
	factors = {}
	for row in rows:
		if not row.s_warehouse or row.t_warehouse or flt(row.transfer_qty) <= 0:
			return None, "A feeding entry has an invalid source or stock quantity."
		key = (row.item_code, row.stock_uom)
		if key not in factors:
			factors[key] = to_kg(row.item_code, row.stock_uom, 1)
		factor = factors[key]
		if factor is None or not isfinite(factor) or factor <= 0:
			return None, "Configure a valid Item UOM conversion to Kg for every feed Item."
		quantity = flt(row.transfer_qty) * factor
		if not isfinite(quantity):
			return None, "A feeding entry has an invalid stock quantity."
		total += quantity
	return round(total, 3), None


def response(value, scope, reason):
	return {
		"value": value,
		"fieldtype": "Float",
		"precision": 3,
		"uom": "Kg",
		"reason": _(reason) if reason else None,
		"from_date": str(scope["from_date"]),
		"to_date": str(scope["to_date"]),
		"route": ["List", "Stock Entry", "List"],
		"route_options": {
			"company": scope["company"],
			"docstatus": 1,
			"stock_entry_type": "Feeding",
			"purpose": "Material Issue",
			"lvm_batch": ["in", scope.get("batch_names", [])],
			"posting_date": ["between", [str(scope["from_date"]), str(scope["to_date"])]],
			**({"lvm_batch": scope["batch"]} if scope.get("batch") else {}),
			**({"lvm_livestock_house": scope["warehouse"]} if scope.get("warehouse") else {}),
		},
	}
