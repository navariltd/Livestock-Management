# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

"""Latest measured interval FCR, aggregated by feed kg / biomass gain kg."""

import frappe
from frappe import _
from frappe.utils import add_days, get_first_day, getdate, nowdate

from livestock_management.livestock_management.batch_stock import get_batch_movements
from livestock_management.livestock_management.dashboard_chart_source.daily_population.daily_population import (
	validate_scope,
)
from livestock_management.livestock_management.number_card.feed_consumed.feed_consumed import sum_feed_kg
from livestock_management.livestock_management.performance_fcr import calculate_fcr as calculate_interval_fcr


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
	return calculate_interval_fcr(movements, weights, entries, rows, from_date, sum_feed_kg)


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
