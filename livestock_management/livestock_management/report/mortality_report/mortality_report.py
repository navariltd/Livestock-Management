# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _


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


def get_columns() -> list[dict]:
	"""Return columns for the report.

	One field definition per column, just like a DocType field definition.
	"""
	return [
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Stock Entry"),
			"fieldname": "stock_entry",
			"fieldtype": "Link",
			"options": "Stock Entry",
			"width": 180,
		},
		{
			"label": _("Batch"),
			"fieldname": "batch",
			"fieldtype": "Link",
			"options": "Batch",
			"width": 140,
		},
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 170,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "s_warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{
			"label": _("Quantity"),
			"fieldname": "quantity",
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"label": _("Opening Qty"),  # sle.qty_after_transaction + abs(sle.actual_qty)
			"fieldname": "opening_qty",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Closing Qty"),  # sle.qty_after_transaction
			"fieldname": "closing_qty",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Dead Stock"),  # abs(sle.actual_qty) if sle.actual_qty < 0 else 0
			"fieldname": "dead_stock",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Mortality Rate"),
			"fieldname": "mortality_rate",
			"fieldtype": "Percent",
			"width": 120,
		},
		{
			"label": _("Valuation Rate"),
			"fieldname": "valuation_rate",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": _("Total Cost"),
			"fieldname": "total_cost",
			"fieldtype": "Currency",
			"width": 130,
		},
	]


def get_conditions(filters: frappe._dict) -> tuple[list[str], dict]:
	conditions = ["se.stock_entry_type = 'Mortality'", "se.docstatus = 1"]
	params = {}

	if filters.get("company"):
		conditions.append("se.company = %(company)s")
		params["company"] = filters.company

	if filters.get("stock_entry"):
		conditions.append("se.name = %(stock_entry)s")
		params["stock_entry"] = filters.stock_entry

	if filters.get("posting_date"):
		conditions.append("se.posting_date = %(posting_date)s")
		params["posting_date"] = filters.posting_date

	if filters.get("warehouse"):
		conditions.append(
			"""EXISTS (
				SELECT 1
				FROM `tabStock Entry Detail` sed_filter
				WHERE sed_filter.parent = se.name
					AND sed_filter.s_warehouse = %(warehouse)s
			)"""
		)
		params["warehouse"] = filters.warehouse

	return conditions, params


def get_data(filters: dict | None = None) -> list[dict]:
	"""Return data for the mortality report."""

	filters = frappe._dict(filters or {})
	conditions, params = get_conditions(filters)
	where_clause = " AND ".join(conditions)

	stock_entries = frappe.db.sql(
		f"""
			SELECT
				se.posting_date,
				se.posting_time,
				se.name AS stock_entry,
				se.lvm_batch AS batch,
				SUM(sle.qty_after_transaction + ABS(sle.actual_qty)) AS opening_qty,
				SUM(sle.qty_after_transaction) AS closing_qty,
				SUM(ABS(sle.actual_qty)) AS dead_stock,
				CASE
					WHEN SUM(sle.qty_after_transaction + ABS(sle.actual_qty)) = 0 THEN 0
					ELSE (
						SUM(ABS(sle.actual_qty))
						/ SUM(sle.qty_after_transaction + ABS(sle.actual_qty))
					) * 100
				END AS mortality_rate,
				SUM(ABS(sle.actual_qty) * sle.valuation_rate) AS total_cost
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Ledger Entry` sle
				ON sle.voucher_no = se.name
			WHERE {where_clause}
			GROUP BY se.name, se.posting_date, se.posting_time, se.lvm_batch
			ORDER BY se.posting_date DESC, se.posting_time DESC, se.name DESC
		""",
		params,
		as_dict=True,
	)

	if not stock_entries:
		return []

	stock_entry_names = [entry.stock_entry for entry in stock_entries]
	detail_conditions = ["sed.parent IN %(stock_entries)s"]
	detail_params = {"stock_entries": stock_entry_names}

	if filters and filters.get("warehouse"):
		detail_conditions.append("sed.s_warehouse = %(warehouse)s")
		detail_params["warehouse"] = filters.warehouse

	if filters and filters.get("item_code"):
		detail_conditions.append("sed.item_code = %(item_code)s")
		detail_params["item_code"] = filters.item_code

	details = frappe.db.sql(
		f"""
			SELECT
				sed.parent AS stock_entry,
				sed.idx,
				sed.item_code,
				sed.batch_no AS batch,
				sed.s_warehouse,
				sed.qty AS quantity,
				sed.valuation_rate,
				(sed.qty * sed.valuation_rate) AS total_cost
			FROM `tabStock Entry Detail` sed
			WHERE {" AND ".join(detail_conditions)}
			ORDER BY sed.parent, sed.idx
		""",
		detail_params,
		as_dict=True,
	)

	details_by_stock_entry = {}
	for detail in details:
		details_by_stock_entry.setdefault(detail.stock_entry, []).append(detail)

	data = []
	for stock_entry_index, stock_entry in enumerate(stock_entries, start=1):
		parent_row_index = str(stock_entry_index)
		data.append(
			{
				"posting_date": stock_entry.posting_date,
				"stock_entry": stock_entry.stock_entry,
				"batch": stock_entry.batch,
				"opening_qty": stock_entry.opening_qty,
				"closing_qty": stock_entry.closing_qty,
				"dead_stock": stock_entry.dead_stock,
				"mortality_rate": stock_entry.mortality_rate,
				"total_cost": stock_entry.total_cost,
				"indent": 0,
				"is_group": 1,
			}
		)

		for _idx, detail in enumerate(details_by_stock_entry.get(stock_entry.stock_entry, []), start=1):
			data.append(
				{
					"parent_row_index": parent_row_index,
					"stock_entry": detail.stock_entry,
					"batch": detail.batch,
					"item_code": detail.item_code,
					"s_warehouse": detail.s_warehouse,
					"quantity": detail.quantity,
					"valuation_rate": detail.valuation_rate,
					"total_cost": detail.total_cost,
					"indent": 1,
				}
			)

	return data
