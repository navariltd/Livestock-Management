# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

"""Period survival for the permitted, explicitly classified livestock population."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate, nowdate

from livestock_management.livestock_management.batch_stock import get_batch_movements
from livestock_management.livestock_management.dashboard_chart_source.daily_population.daily_population import (
	validate_scope,
)


@frappe.whitelist()
def get(filters: str | dict | list | None = None):
	parsed = frappe.parse_json(filters) if isinstance(filters, str) else filters
	if parsed is None or parsed == []:
		parsed = {}
	if not isinstance(parsed, dict):
		frappe.throw(_("Invalid Survival Percentage filters."))
	scope = dict(parsed)
	scope["company"] = scope.get("company") or frappe.defaults.get_user_default("Company")
	if not scope["company"]:
		frappe.throw(_("Set a default Company or select Company in the card filters."))
	scope["to_date"] = getdate(scope.get("to_date") or nowdate())
	scope["from_date"] = getdate(scope.get("from_date") or get_first_day(scope["to_date"]))
	if scope["from_date"] > scope["to_date"] or scope["to_date"] > getdate(nowdate()):
		frappe.throw(_("Select a historical date range with From Date on or before To Date."))
	validate_scope(scope)
	frappe.has_permission("Stock Entry", "read", throw=True)
	item_filters = {"is_stock_item": 1, "has_batch_no": 1, "stock_uom": ["in", ["Nos", "Unit"]]}
	if scope.get("item_code"):
		item_filters["name"] = scope["item_code"]
	items = frappe.get_list("Item", filters=item_filters, pluck="name", limit_page_length=0)
	batches = []
	if items:
		batch_filters = {"lvm_is_livestock_item": 1, "item": ["in", items]}
		if scope.get("batch"):
			batch_filters["name"] = scope["batch"]
		batches = frappe.get_list("Batch", filters=batch_filters, pluck="name", limit_page_length=0)
	scope["item_codes"] = items
	movements = get_batch_movements(scope, batches)
	sources = list(
		{
			m.voucher_no
			for rows in movements.values()
			for m in rows
			if m.date >= scope["from_date"] and m.voucher_type == "Stock Entry"
		}
	)
	entries = (
		frappe.get_list(
			"Stock Entry",
			filters={"name": ["in", sources], "company": scope["company"], "docstatus": 1},
			fields=["name", "stock_entry_type", "purpose"],
			limit_page_length=0,
		)
		if sources
		else []
	)
	value, reason, exposure, deaths = calculate_survival(
		movements, {e.name: e for e in entries}, scope["from_date"]
	)
	return {
		"value": value if value is not None else _("Unavailable"),
		"fieldtype": "Percent" if value is not None else "Data",
		"precision": 2,
		"reason": _(reason) if reason else None,
		"population_exposed": exposure,
		"deaths": deaths,
		"from_date": str(scope["from_date"]),
		"to_date": str(scope["to_date"]),
		"route": ["query-report", "Livestock Batch Performance report"],
		"route_options": {
			key: str(scope[key])
			for key in ("company", "item_code", "batch", "warehouse", "from_date", "to_date")
			if scope.get(key)
		},
	}


def calculate_survival(movements, entries, from_date):
	"""Weight the combined rate by animals exposed, never by averaging batch rates."""
	opening = 0.0
	period = defaultdict(float)
	for rows in movements.values():
		batch_opening = sum(flt(m.qty) for m in rows if getdate(m.date) < getdate(from_date))
		batch_closing = sum(flt(m.qty) for m in rows)
		if batch_opening < -0.000001 or batch_closing < -0.000001:
			return None, "A Batch has an invalid negative stock balance.", None, None
		for movement in rows:
			if getdate(movement.date) < getdate(from_date):
				opening += flt(movement.qty)
			else:
				period[(movement.voucher_type, movement.voucher_no)] += flt(movement.qty)
	introduced, deaths, closing = 0.0, 0.0, opening
	for (kind, name), qty in period.items():
		closing += qty
		if kind == "Stock Reconciliation":
			return None, "Stock corrections make survival unavailable for this period.", None, None
		if kind == "Stock Entry":
			entry = entries.get(name)
			if not entry:
				return None, "A stock movement cannot be classified with your current access.", None, None
			if entry.stock_entry_type == "Mortality":
				if entry.purpose != "Material Issue" or qty >= 0:
					return None, "Invalid mortality stock movement.", None, None
				deaths -= qty
			elif entry.purpose == "Repack" and abs(qty) > 0.000001:
				return (
					None,
					"Batch transformations require complete lineage before calculating survival.",
					None,
					None,
				)
			elif entry.purpose == "Material Issue" and entry.stock_entry_type != "Culling":
				return None, "An animal issue is not classified as mortality or culling.", None, None
		elif kind not in ("Purchase Receipt", "Purchase Invoice", "Delivery Note", "Sales Invoice"):
			return None, "Unsupported stock movement in the selected period.", None, None
		introduced += max(qty, 0)
	exposure = opening + introduced
	if opening < 0 or closing < -0.000001 or exposure <= 0 or deaths > exposure:
		return None, "No reliable positive population denominator is available.", exposure, deaths
	return round(100 * (exposure - deaths) / exposure, 2), None, exposure, deaths
