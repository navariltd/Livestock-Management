# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from collections import defaultdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, nowdate
from frappe.utils.dateutils import get_from_date_from_timespan

from livestock_management.livestock_management.batch_stock import get_batch_movements
from livestock_management.livestock_management.dashboard_chart_source.daily_population.daily_population import (
	validate_scope,
)


@frappe.whitelist()
def get(
	chart_name: str | None = None,
	chart: str | dict | None = None,
	no_cache: int | str | None = None,
	filters: str | dict | list | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	timespan: str | None = None,
	time_interval: str | None = None,
	heatmap_year: str | int | None = None,
	refresh: int | str | None = None,
) -> dict[str, Any]:
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
		raise frappe.ValidationError(_("Invalid chart filters."))
	chart_filters["company"] = chart_filters.get("company") or frappe.defaults.get_user_default("Company")
	if not chart_filters["company"]:
		frappe.throw(_("Set a default Company or select Company in the chart filters."))
	interval = time_interval or (settings.get("time_interval") if settings else None) or "Daily"
	if interval != "Daily":
		frappe.throw(_("Mortality Trend supports the Daily interval only."))
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
		frappe.throw(_("Mortality Trend displays historical mortality; To Date cannot be in the future."))
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
	frappe.has_permission("Stock Entry", "read", throw=True)
	# Permission-aware parents determine which ledger vouchers may contribute.
	vouchers = (
		frappe.get_list(
			"Stock Entry",
			filters={
				"company": chart_filters["company"],
				"docstatus": 1,
				"stock_entry_type": "Mortality",
				"purpose": "Material Issue",
				"posting_date": ["between", [chart_filters["from_date"], chart_filters["to_date"]]],
			},
			pluck="name",
			limit_page_length=0,
		)
		if batch_names
		else []
	)
	movements = get_batch_movements(chart_filters, batch_names) if vouchers else {}
	labels, values = daily_deaths(
		movements, set(vouchers), chart_filters["from_date"], chart_filters["to_date"]
	)
	return {
		"labels": labels,
		"datasets": [{"name": _("Animals Lost"), "values": values}],
		"type": "line",
	}


def daily_deaths(movements, vouchers, from_date, to_date):
	"""Sum outgoing animals once per ledger batch allocation, rather than counting documents."""
	start, end = getdate(from_date), getdate(to_date)
	deaths = defaultdict(float)
	for batch_moves in movements.values():
		for movement in batch_moves:
			day = getdate(movement.date)
			if (
				start <= day <= end
				and movement.voucher_type == "Stock Entry"
				and movement.voucher_no in vouchers
				and flt(movement.qty) < 0
			):
				deaths[day] -= flt(movement.qty)
	labels, values = [], []
	for offset in range(date_diff(end, start) + 1):
		day = getdate(add_days(start, offset))
		labels.append(str(day))
		values.append(round(deaths[day], 6))
	return labels, values
