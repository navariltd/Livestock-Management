# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, nowdate


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns() -> list[dict]:
	return [
		{
			"label": _("#"),
			"fieldname": "row_index",
			"fieldtype": "Data",
			"width": 80,
		},
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
			"label": _("Age in Days"),
			"fieldname": "age_in_days",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": _("Age in Weeks"),
			"fieldname": "age_in_weeks",
			"fieldtype": "Int",
			"width": 110,
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
			"fieldname": "t_warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{
			"label": _("Total Produce"),
			"fieldname": "total_produce",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Opening Stock"),
			"fieldname": "opening_stock",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("% Produce"),
			"fieldname": "produce_percent",
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


def get_data(filters: dict | None = None) -> list[dict]:
	filters = frappe._dict(filters or {})
	params = {
		key: filters.get(key) or None
		for key in ["company", "stock_entry", "from_date", "to_date", "batch", "warehouse", "item_code"]
	}

	stock_entries = frappe.db.sql(
		"""
			SELECT
				se.posting_date,
				se.posting_time,
				se.name AS stock_entry,
				se.lvm_batch AS batch,
				b.manufacturing_date,
				SUM(sed.qty) AS total_produce,
				COALESCE(b.batch_qty, 0) AS opening_stock,
				CASE
					WHEN COALESCE(b.batch_qty, 0) = 0 THEN 0
					ELSE (
						SUM(sed.qty)
						/ COALESCE(b.batch_qty, 0)
					) * 100
				END AS produce_percent,
				SUM(sed.qty * sed.valuation_rate) AS total_cost
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed
				ON sed.parent = se.name
			LEFT JOIN `tabBatch` b
				ON b.name = se.lvm_batch
			WHERE se.stock_entry_type = 'Production' AND se.docstatus = 1
				AND (%(company)s IS NULL OR se.company = %(company)s)
				AND (%(stock_entry)s IS NULL OR se.name = %(stock_entry)s)
				AND (%(from_date)s IS NULL OR se.posting_date >= %(from_date)s)
				AND (%(to_date)s IS NULL OR se.posting_date <= %(to_date)s)
				AND (%(batch)s IS NULL OR se.lvm_batch = %(batch)s)
				AND (%(warehouse)s IS NULL OR EXISTS (SELECT 1 FROM `tabStock Entry Detail` sed_filter WHERE sed_filter.parent = se.name AND sed_filter.t_warehouse = %(warehouse)s))
				AND (%(item_code)s IS NULL OR EXISTS (SELECT 1 FROM `tabStock Entry Detail` sed_filter WHERE sed_filter.parent = se.name AND sed_filter.item_code = %(item_code)s))
				AND sed.t_warehouse IS NOT NULL
			GROUP BY
				se.name,
				se.posting_date,
				se.posting_time,
				se.lvm_batch,
				b.manufacturing_date,
				b.batch_qty
			ORDER BY se.posting_date DESC, se.posting_time DESC, se.name DESC
		""",
		params,
		as_dict=True,
	)

	if not stock_entries:
		return []

	stock_entry_names = [entry.stock_entry for entry in stock_entries]
	detail_params = {**params, "stock_entries": stock_entry_names}

	details = frappe.db.sql(
		"""
			SELECT
				sed.parent AS stock_entry,
				sed.idx,
				sed.item_code,
				sed.batch_no AS batch,
				sed.t_warehouse,
				sed.qty AS total_produce,
				COALESCE(b.batch_qty, 0) AS opening_stock,
				CASE
					WHEN COALESCE(b.batch_qty, 0) = 0 THEN 0
					ELSE (
						sed.qty
						/ COALESCE(b.batch_qty, 0)
					) * 100
				END AS produce_percent,
				sed.valuation_rate,
				(sed.qty * sed.valuation_rate) AS total_cost
			FROM `tabStock Entry Detail` sed
			INNER JOIN `tabStock Entry` se
				ON se.name = sed.parent
			LEFT JOIN `tabBatch` b
				ON b.name = se.lvm_batch
			WHERE sed.parent IN %(stock_entries)s AND sed.t_warehouse IS NOT NULL
				AND (%(warehouse)s IS NULL OR sed.t_warehouse = %(warehouse)s)
				AND (%(item_code)s IS NULL OR sed.item_code = %(item_code)s)
			ORDER BY sed.parent, sed.idx
		""",
		detail_params,
		as_dict=True,
	)

	details_by_stock_entry = {}
	for detail in details:
		details_by_stock_entry.setdefault(detail.stock_entry, []).append(detail)

	data = []
	today = nowdate()
	for stock_entry_index, stock_entry in enumerate(stock_entries, start=1):
		parent_row_index = str(stock_entry_index)
		age_in_days = None
		age_in_weeks = None
		if stock_entry.manufacturing_date:
			age_in_days = date_diff(today, stock_entry.manufacturing_date)
			age_in_weeks = age_in_days // 7

		data.append(
			{
				"row_index": parent_row_index,
				"posting_date": stock_entry.posting_date,
				"stock_entry": stock_entry.stock_entry,
				"batch": stock_entry.batch,
				"age_in_days": age_in_days,
				"age_in_weeks": age_in_weeks,
				"total_produce": stock_entry.total_produce,
				"opening_stock": stock_entry.opening_stock,
				"produce_percent": stock_entry.produce_percent,
				"total_cost": stock_entry.total_cost,
				"indent": 0,
				"is_group": 1,
			}
		)

		for detail_index, detail in enumerate(
			details_by_stock_entry.get(stock_entry.stock_entry, []), start=1
		):
			data.append(
				{
					"row_index": f"{parent_row_index}.{detail_index}",
					"parent_row_index": parent_row_index,
					"stock_entry": detail.stock_entry,
					"batch": detail.batch,
					"age_in_days": age_in_days,
					"age_in_weeks": age_in_weeks,
					"item_code": detail.item_code,
					"t_warehouse": detail.t_warehouse,
					"total_produce": detail.total_produce,
					"opening_stock": detail.opening_stock,
					"produce_percent": detail.produce_percent,
					"valuation_rate": detail.valuation_rate,
					"total_cost": detail.total_cost,
					"indent": 1,
				}
			)

	return data
