# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import DocType

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

	if filters.get("posting_date"):
		query = query.where(stock_entry.posting_date == filters.posting_date)

	if filters.get("company"):
		query = query.where(stock_entry.company == filters.company)

	if filters.get("item_code"):
		query = query.where(stock_entry_detail.item_code == filters.item_code)

	if filters.get("batch"):
		query = query.where(stock_entry.lvm_batch == filters.batch)

	if filters.get("warehouse"):
		query = query.where(stock_entry_detail.s_warehouse == filters.warehouse)

	return query


def get_data(filters: dict | None = None) -> list[dict]:
	filters = frappe._dict(filters or {})

	query = (
		frappe.qb.from_(stock_entry)
		.inner_join(stock_entry_detail)
		.on(stock_entry_detail.parent == stock_entry.name)
		.select(
			stock_entry.posting_date.as_("posting_date"),
			stock_entry.name.as_("stock_entry"),
			stock_entry.lvm_batch.as_("batch"),
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

	return query.run(as_dict=True)


# def get_data(filters: dict | None = None) -> list[dict]:
# 	filters = frappe._dict(filters or {})

# 	conditions = ["se.docstatus = 1"]

# 	conditions.append("se.stock_entry_type = %(stock_entry_type)s")

# 	query_filters = {
# 		"stock_entry_type": "Feeding",
# 	}

# 	if filters and filters.get("posting_date"):
# 		conditions.append("se.posting_date = %(posting_date)s")
# 		query_filters["posting_date"] = filters['posting_date']

# 	if filters and filters.get("company"):
# 		conditions.append("se.company = %(company)s")
# 		query_filters["company"] = filters['company']

# 	if filters and filters.get("item_code"):
# 		conditions.append("sed.item_code = %(item_code)s")
# 		query_filters["item_code"] = filters['item_code']

# 	if filters and filters.get("batch"):
# 		conditions.append("se.lvm_batch = %(batch)s")
# 		query_filters["batch"] = filters['batch']

# 	if filters and filters.get("warehouse"):
# 		conditions.append("sed.s_warehouse = %(warehouse)s")
# 		query_filters["warehouse"] = filters['warehouse']

# 	return frappe.db.sql(
# 		f"""
# 		SELECT
# 			se.posting_date AS posting_date,
# 			se.name AS stock_entry,
# 			se.lvm_batch AS batch,
# 			sed.item_code AS item_code,
# 			sed.s_warehouse AS s_warehouse,
# 			sed.qty AS actual_qty,
# 			sed.valuation_rate AS valuation_rate
# 		FROM
# 			`tabStock Entry` se
# 		INNER JOIN
# 			`tabStock Entry Detail` sed
# 			ON sed.parent = se.name
# 		WHERE
# 			{" AND ".join(conditions)}
# 		ORDER BY
# 			se.posting_date DESC,
# 			se.posting_time DESC,
# 			se.name DESC
# 		""",
# 		query_filters,
# 		as_dict=True,
# 	)
