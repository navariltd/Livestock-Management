# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Coalesce

stock_entry = DocType("Stock Entry")
stock_entry_detail = DocType("Stock Entry Detail")
item_price = DocType("Item Price")


def execute(filters: dict | None = None):
	"""Return columns and data for the report.

	This is the main entry point for the report. It accepts the filters as a
	dictionary and should return columns and data. It is called by the framework
	every time the report is refreshed or a filter is updated.
	"""
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)

	return columns, data


def execute_snapshot_report(filters: dict | None = None):
	"""Return columns and data for the report.

	This is the main entry point for snapshot report. When 'Synced
	Report' is enabled in report, framework will call this method
	every time the report is refreshed or a filter is updated. It
	accepts the same filters as normal execute. But a utility method -
	get_latest_sync, is also imported.

	"""
	from frappe.database.duckdb.database import get_latest_sync

	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns() -> list[dict]:
	"""Return columns for the report.

	One field definition per column, just like a DocType field definition.
	"""
	return [
		{
			"label": _("#"),
			"fieldname": "row_index",
			"fieldtype": "Data",
			"width": 60,
		},
		{
			"label": _("Repack Entry"),
			"fieldname": "repack_entry",
			"fieldtype": "Link",
			"options": "Stock Entry",
		},
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
		},
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
		},
		{
			"label": _("Item"),
			"fieldname": "item_name",
			"fieldtype": "Link",
			"options": "Item",
		},
		{
			"label": _("Source Warehouse"),
			"fieldname": "s_warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
		},
		{
			"label": _("Target Warehouse"),
			"fieldname": "t_warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
		},
		{
			"label": _("Quantity"),
			"fieldname": "qty",
			"fieldtype": "Float",
		},
		{
			"label": _("Valuation Rate"),
			"fieldname": "valuation_rate",
			"fieldtype": "Currency",
		},
		{
			"label": _("Selling Price"),
			"fieldname": "selling_price",
			"fieldtype": "Currency",
		},
		{
			"label": _("Total Valuation"),
			"fieldname": "total_valuation",
			"fieldtype": "Currency",
		},
		{
			"label": _("Total Selling"),
			"fieldname": "total_selling",
			"fieldtype": "Currency",
		},
		{
			"label": _("Profit"),
			"fieldname": "profit",
			"fieldtype": "Currency",
		},
		{
			"label": _("Opportunity Forgone"),
			"fieldname": "opportunity_forgone",
			"fieldtype": "Currency",
		},
	]


def get_data(filters: frappe._dict) -> list[dict]:
	filters = frappe._dict(filters or {})
	price_list = filters.get("selling_price_list") or frappe.db.get_single_value(
		"Selling Settings", "selling_price_list"
	)

	price_query = (
		frappe.qb.from_(item_price)
		.select(item_price.price_list_rate)
		.where(item_price.item_code == stock_entry_detail.item_code)
		.where(item_price.price_list == price_list)
		.where(item_price.selling == 1)
		.where((item_price.valid_from.isnull()) | (item_price.valid_from <= stock_entry.posting_date))
		.where((item_price.valid_upto.isnull()) | (item_price.valid_upto >= stock_entry.posting_date))
		.orderby(item_price.valid_from, order=frappe.qb.desc)
		.orderby(item_price.creation, order=frappe.qb.desc)
		.limit(1)
	)

	query = (
		frappe.qb.from_(stock_entry)
		.inner_join(stock_entry_detail)
		.on(stock_entry_detail.parent == stock_entry.name)
		.select(
			stock_entry.name.as_("repack_entry"),
			stock_entry.posting_date,
			stock_entry.posting_time,
			stock_entry_detail.idx,
			stock_entry_detail.item_code,
			stock_entry_detail.item_name,
			stock_entry_detail.s_warehouse,
			stock_entry_detail.t_warehouse,
			stock_entry_detail.qty,
			stock_entry_detail.valuation_rate,
			Coalesce(price_query, 0).as_("selling_price"),
		)
		.where(stock_entry.stock_entry_type == "Repack")
		.where(stock_entry.docstatus == 1)
		.where((stock_entry_detail.s_warehouse.isnotnull()) | (stock_entry_detail.t_warehouse.isnotnull()))
		.orderby(stock_entry.posting_date, order=frappe.qb.desc)
		.orderby(stock_entry.posting_time, order=frappe.qb.desc)
		.orderby(stock_entry.name, order=frappe.qb.desc)
		.orderby(stock_entry_detail.idx)
	)

	query = apply_filters(query, filters)
	return build_tree_rows(query.run(as_dict=True))


def apply_filters(query, filters: frappe._dict):
	if filters.get("company"):
		query = query.where(stock_entry.company == filters.company)
	if filters.get("from_date"):
		query = query.where(stock_entry.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(stock_entry.posting_date <= filters.to_date)
	if filters.get("repack_entry"):
		query = query.where(stock_entry.name == filters.repack_entry)

	return query


def build_tree_rows(details: list[dict]) -> list[dict]:
	entries_by_repack = {}
	for detail in details:
		entries_by_repack.setdefault(detail.repack_entry, []).append(detail)

	data = []
	for entry_index, (repack_entry, entry_details) in enumerate(entries_by_repack.items(), start=1):
		parent_index = str(entry_index)
		for detail in entry_details:
			total_selling = detail.selling_price * detail.qty
			total_valuation = detail.valuation_rate * detail.qty
			detail.profit = total_selling - total_valuation

		source_profit = sum(detail.profit for detail in entry_details if detail.s_warehouse)
		destination_profit = sum(detail.profit for detail in entry_details if detail.t_warehouse)
		data.append(
			{
				"row_index": parent_index,
				"repack_entry": repack_entry,
				"posting_date": entry_details[0].posting_date,
				"opportunity_forgone": source_profit - destination_profit,
				"indent": 0,
				"is_group": 1,
			}
		)

		for detail_index, detail in enumerate(entry_details, start=1):
			data.append(
				{
					"row_index": f"{parent_index}.{detail_index}",
					"parent_row_index": parent_index,
					"repack_entry": repack_entry,
					"posting_date": detail.posting_date,
					"item_code": detail.item_code,
					"item_name": detail.item_name,
					"s_warehouse": detail.s_warehouse,
					"t_warehouse": detail.t_warehouse,
					"qty": detail.qty,
					"valuation_rate": detail.valuation_rate,
					"selling_price": detail.selling_price,
					"total_valuation": detail.qty * detail.valuation_rate,
					"total_selling": detail.qty * detail.selling_price,
					"profit": detail.profit,
					"indent": 1,
				}
			)

	return data
