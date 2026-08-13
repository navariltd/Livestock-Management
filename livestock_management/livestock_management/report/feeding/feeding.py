# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.utils import date_diff, nowdate

batch = DocType("Batch")
stock_entry = DocType("Stock Entry")
stock_entry_detail = DocType("Stock Entry Detail")


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns() -> list[dict]:
	return [
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
		},
		{
			"label": _("Stock Entry"),
			"fieldname": "stock_entry",
			"fieldtype": "Link",
			"options": "Stock Entry",
		},
		{
			"label": _("Batch"),
			"fieldname": "batch",
			"fieldtype": "Link",
			"options": "Batch",
		},
		{
			"label": _("Batch Qty"),
			"fieldname": "batch_qty",
			"fieldtype": "Float",
		},
		{
			"label": _("Age in Days"),
			"fieldname": "age_in_days",
			"fieldtype": "Int",
		},
		{
			"label": _("Age in Weeks"),
			"fieldname": "age_in_weeks",
			"fieldtype": "Int",
		},
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
		},
		{
			"label": _("Warehouse"),
			"fieldname": "s_warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
		},
		{
			"label": _("Quantity"),
			"fieldname": "actual_qty",
			"fieldtype": "Int",
		},
		{
			"label": _("Valuation Rate"),
			"fieldname": "valuation_rate",
			"fieldtype": "Currency",
		},
		{
			"label": _("Total Cost"),
			"fieldname": "total_cost",
			"fieldtype": "Currency",
		},
	]


def apply_filters(query, filters, stock_entry, stock_entry_detail):
	if not filters:
		return query

	if filters.get("from_date"):
		query = query.where(stock_entry.posting_date >= filters.get("from_date"))

	if filters.get("to_date"):
		query = query.where(stock_entry.posting_date <= filters.get("to_date"))

	if filters.get("company"):
		query = query.where(stock_entry.company == filters.get("company"))

	if filters.get("stock_entry"):
		query = query.where(stock_entry.name == filters.get("stock_entry"))

	if filters.get("item_code"):
		query = query.where(stock_entry_detail.item_code == filters.get("item_code"))

	if filters.get("batch"):
		query = query.where(stock_entry.lvm_batch == filters.get("batch"))

	if filters.get("warehouse"):
		query = query.where(stock_entry_detail.s_warehouse == filters.get("warehouse"))

	return query


def get_data(filters: dict | None = None) -> list[dict]:
	filters = frappe._dict(filters or {})

	query = (
		frappe.qb.from_(stock_entry)
		.inner_join(stock_entry_detail)
		.on(stock_entry_detail.parent == stock_entry.name)
		.left_join(batch)
		.on(batch.name == stock_entry.lvm_batch)
		.select(
			stock_entry.posting_date.as_("posting_date"),
			stock_entry.name.as_("stock_entry"),
			stock_entry.lvm_batch.as_("batch"),
			batch.manufacturing_date.as_("manufacturing_date"),
			batch.batch_qty.as_("batch_qty"),
			stock_entry_detail.item_code.as_("item_code"),
			stock_entry_detail.s_warehouse.as_("s_warehouse"),
			stock_entry_detail.qty.as_("actual_qty"),
			stock_entry_detail.valuation_rate.as_("valuation_rate"),
			(stock_entry_detail.qty * stock_entry_detail.valuation_rate).as_("total_cost"),
		)
		.where(stock_entry.docstatus == 1)
		.where(stock_entry.stock_entry_type == "Feeding")
		.orderby(stock_entry.posting_date, order=frappe.qb.desc)
		.orderby(stock_entry.posting_time, order=frappe.qb.desc)
		.orderby(stock_entry.name, order=frappe.qb.desc)
	)

	query = apply_filters(query, filters, stock_entry, stock_entry_detail)

	data = query.run(as_dict=True)
	today = nowdate()

	for row in data:
		manufacturing_date = row.get("manufacturing_date")
		if not manufacturing_date:
			continue

		age_in_days = date_diff(today, manufacturing_date)
		row["age_in_days"] = age_in_days
		row["age_in_weeks"] = age_in_days // 7

	return data
