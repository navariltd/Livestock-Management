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
	columns = get_columns()
	data = get_data()

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
			"label": _("Opening Qty"),  # sle.qty_after_transaction + abs(sle.actual_qty)
			"fieldname": "opening_qty",
			"fieldtype": "Int",
		},
		{
			"label": _("Closing Qty"),  # sle.qty_after_transaction
			"fieldname": "closing_qty",
			"fieldtype": "Int",
		},
		{
			"label": _("Dead Stock"),  # abs(sle.actual_qty) if sle.actual_qty < 0 else 0
			"fieldname": "dead_stock",
			"fieldtype": "Int",
		},
		{
			"label": _("Mortality Rate"),
			"fieldname": "mortality_rate",
			"fieldtype": "Percent",
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


def get_data(filters: dict | None = None) -> list[dict]:
	"""Return data for the mortality report."""

	# Base condition to ensure we only get mortality-related stock entries
	conditions = "se.stock_entry_type = 'Mortality' AND se.docstatus = 1"

	# Apply filters if provided
	if filters:
		if filters.get("batch"):
			conditions += f" AND sle.batch_no = '{filters.get('batch')}'"
		if filters.get("from_date"):
			conditions += f" AND sle.posting_date >= '{filters.get('from_date')}'"
		if filters.get("to_date"):
			conditions += f" AND sle.posting_date <= '{filters.get('to_date')}'"

	# Query Stock Ledger Entry joined with Stock Entry
	data = frappe.db.sql(
		f"""
        SELECT
            sle.posting_date,
            sle.voucher_no as stock_entry,
            se.lvm_batch as batch,
            sle.item_code,
            sle.warehouse as s_warehouse,
            sle.qty_after_transaction as closing_qty,
            (sle.qty_after_transaction + ABS(sle.actual_qty)) as opening_qty,
            ABS(sle.actual_qty) as dead_stock,
            CASE
                WHEN (sle.qty_after_transaction + ABS(sle.actual_qty)) = 0 THEN 0
                ELSE (ABS(sle.actual_qty) / (sle.qty_after_transaction + ABS(sle.actual_qty))) * 100
            END as mortality_rate,
            sle.valuation_rate,
            (ABS(sle.actual_qty) * sle.valuation_rate) as total_cost
        FROM `tabStock Ledger Entry` sle
        JOIN `tabStock Entry` se ON sle.voucher_no = se.name
        WHERE {conditions}
        ORDER BY sle.posting_date DESC
    """,
		as_dict=True,
	)

	return data
