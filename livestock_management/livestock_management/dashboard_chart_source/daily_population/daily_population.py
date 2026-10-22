# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from collections import defaultdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, nowdate
from frappe.utils.dateutils import get_from_date_from_timespan

from livestock_management.livestock_management.batch_stock import get_batch_movements


@frappe.whitelist()
def get(
	chart_name: str | None = None,
	chart: str | dict | None = None,
	no_cache: int | str | None = None,
	filters: str | dict | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	timespan: str | None = None,
	time_interval: str | None = None,
	heatmap_year: str | int | None = None,
	refresh: int | str | None = None,
):
	# Deliberately avoid cache_source: its chart-name cache is shared across users/filters.
	# Re-evaluate current permissions on every request, including Refresh.
	settings = None
	if chart_name:
		settings = frappe.get_doc("Dashboard Chart", chart_name)
		settings.check_permission("read")
	elif chart:
		settings = frappe._dict(frappe.parse_json(chart) if isinstance(chart, str) else chart)
	if filters is None and settings:
		filters = settings.get("filters_json")
	parsed_filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
	if parsed_filters is None or parsed_filters == []:
		chart_filters: dict[str, Any] = {}
	elif isinstance(parsed_filters, dict):
		chart_filters = dict(parsed_filters)
	else:
		frappe.throw(_("Invalid chart filters."))
		return
	chart_filters["company"] = chart_filters.get("company") or frappe.defaults.get_user_default("Company")
	if not chart_filters["company"]:
		frappe.throw(_("Set a default Company or select Company in the chart filters."))
	interval = time_interval or (settings.get("time_interval") if settings else None) or "Daily"
	if interval != "Daily":
		frappe.throw(_("Daily Population supports the Daily interval only."))
	span = timespan or (settings.get("timespan") if settings else None) or "Last Month"
	end = to_date or (settings.get("to_date") if settings and span == "Select Date Range" else None)
	start = from_date or (settings.get("from_date") if settings and span == "Select Date Range" else None)
	chart_filters["to_date"] = getdate(end or nowdate())
	if span == "Select Date Range" and (not start or not end):
		frappe.throw(_("Select both From Date and To Date."))
	if not start and span not in (
		"Last Year",
		"Last Quarter",
		"Last Month",
		"Last Week",
	):
		frappe.throw(_("Select a valid chart timespan."))
	chart_filters["from_date"] = getdate(start or get_from_date_from_timespan(chart_filters["to_date"], span))
	if chart_filters["from_date"] > chart_filters["to_date"]:
		frappe.throw(_("From Date cannot be after To Date."))
	if date_diff(chart_filters["to_date"], chart_filters["from_date"]) > 366:
		frappe.throw(_("Select a date range of at most 367 days."))
	if chart_filters["to_date"] > getdate(nowdate()):
		frappe.throw(_("Daily Population displays historical balances; To Date cannot be in the future."))
	validate_scope(chart_filters)
	item_filters = {
		"is_stock_item": 1,
		"has_batch_no": 1,
		"stock_uom": ["in", ["Nos", "Unit"]],
	}
	if chart_filters.get("item_code"):
		item_filters["name"] = chart_filters["item_code"]
	item_names = frappe.get_list("Item", filters=item_filters, pluck="name", limit_page_length=0)
	batch_filters = {"lvm_is_livestock_item": 1, "item": ["in", item_names]}
	if chart_filters.get("batch"):
		batch_filters["name"] = chart_filters["batch"]
	batch_names = (
		frappe.get_list("Batch", filters=batch_filters, pluck="name", limit_page_length=0)
		if item_names
		else []
	)
	chart_filters["item_codes"] = item_names
	movements = get_batch_movements(chart_filters, batch_names)
	labels, values = daily_balances(movements, chart_filters["from_date"], chart_filters["to_date"])
	return {
		"labels": labels,
		"datasets": [{"name": _("Closing Population"), "values": values}],
		"type": "line",
	}


def validate_scope(filters):
	frappe.get_doc("Company", filters.company).check_permission("read")
	if not frappe.get_meta("Batch").has_field("lvm_is_livestock_item"):
		frappe.throw(_("Run site migration to install the Batch livestock classification field."))
	if filters.get("item_code"):
		validate_item(filters.item_code)
	if filters.get("batch"):
		batch = frappe.get_doc("Batch", filters.batch)
		batch.check_permission("read")
		if not batch.get("lvm_is_livestock_item"):
			frappe.throw(_("Select a Batch marked Is Livestock Item."))
		if filters.get("item_code") and batch.item != filters.item_code:
			frappe.throw(_("Batch must belong to the selected Livestock Item."))
		validate_item(batch.item)
	if filters.get("warehouse"):
		warehouse = frappe.get_doc("Warehouse", filters.warehouse)
		warehouse.check_permission("read")
		if warehouse.company != filters.company or warehouse.is_group:
			frappe.throw(_("Select a non-group Warehouse belonging to the selected Company."))


def validate_item(name):
	item = frappe.get_doc("Item", name)
	item.check_permission("read")
	if not item.is_stock_item or not item.has_batch_no:
		frappe.throw(_("Select a batch-tracked livestock stock Item."))
	if item.stock_uom not in ("Nos", "Unit"):
		frappe.throw(_("Daily Population requires livestock counted in Nos or Unit."))


def daily_balances(movements, from_date, to_date):
	"""One stock-history pass followed by one date pass; no per-day report queries."""
	start, end = getdate(from_date), getdate(to_date)
	opening = 0.0
	changes = defaultdict(float)
	for batch_moves in movements.values():
		for movement in batch_moves:
			day = getdate(movement.date)
			if day < start:
				opening += flt(movement.qty)
			elif day <= end:
				changes[day] += flt(movement.qty)
	labels, values = [], []
	for offset in range(date_diff(end, start) + 1):
		day = getdate(add_days(start, offset))
		opening += changes[day]
		labels.append(str(day))
		values.append(round(opening, 6))
	return labels, values
