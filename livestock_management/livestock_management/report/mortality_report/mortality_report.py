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
			"label": _("Total Cost"),
			"fieldname": "total_cost",
			"fieldtype": "Currency",
			"width": 130,
		},
	]


def get_data(filters: dict | None = None) -> list[dict]:
	"""Return data for the mortality report."""

	filters = frappe._dict(filters or {})
	params = {
		key: filters.get(key) or None
		for key in ["company", "stock_entry", "from_date", "to_date", "warehouse"]
	}

	stock_entries = frappe.db.sql(
		"""
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
			WHERE se.stock_entry_type = 'Mortality' AND se.docstatus = 1
				AND (%(company)s IS NULL OR se.company = %(company)s)
				AND (%(stock_entry)s IS NULL OR se.name = %(stock_entry)s)
				AND (%(from_date)s IS NULL OR se.posting_date >= %(from_date)s)
				AND (%(to_date)s IS NULL OR se.posting_date <= %(to_date)s)
				AND (%(warehouse)s IS NULL OR EXISTS (SELECT 1 FROM `tabStock Entry Detail` sed_filter WHERE sed_filter.parent = se.name AND sed_filter.s_warehouse = %(warehouse)s))
			GROUP BY se.name, se.posting_date, se.posting_time, se.lvm_batch
			ORDER BY se.posting_date DESC, se.posting_time DESC, se.name DESC
		""",
		params,
		as_dict=True,
	)

	return stock_entries
