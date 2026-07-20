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


def get_conditions(filters: frappe._dict) -> tuple[list[str], dict]:
	conditions = ["se.stock_entry_type = 'Production'", "se.docstatus = 1"]
	params = {}

	if filters.get("company"):
		conditions.append("se.company = %(company)s")
		params["company"] = filters.get("company")

	if filters.get("stock_entry"):
		conditions.append("se.name = %(stock_entry)s")
		params["stock_entry"] = filters.get("stock_entry")

	if filters.get("posting_date"):
		conditions.append("se.posting_date = %(posting_date)s")
		params["posting_date"] = filters.get("posting_date")

	if filters.get("batch"):
		conditions.append("se.lvm_batch = %(batch)s")
		params["batch"] = filters.get("batch")

	if filters.get("warehouse"):
		conditions.append(
			"""EXISTS (
				SELECT 1
				FROM `tabStock Entry Detail` sed_filter
				WHERE sed_filter.parent = se.name
					AND sed_filter.t_warehouse = %(warehouse)s
			)"""
		)
		params["warehouse"] = filters.get("warehouse")

	if filters.get("item_code"):
		conditions.append(
			"""EXISTS (
				SELECT 1
				FROM `tabStock Entry Detail` sed_filter
				WHERE sed_filter.parent = se.name
					AND sed_filter.item_code = %(item_code)s
			)"""
		)
		params["item_code"] = filters.get("item_code")

	return conditions, params


def get_data(filters: dict | None = None) -> list[dict]:
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
			WHERE {where_clause}
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
	detail_conditions = ["sed.parent IN %(stock_entries)s", "sed.t_warehouse IS NOT NULL"]
	detail_params = {"stock_entries": stock_entry_names}

	if filters.get("warehouse"):
		detail_conditions.append("sed.t_warehouse = %(warehouse)s")
		detail_params["warehouse"] = filters.get("warehouse")

	if filters.get("item_code"):
		detail_conditions.append("sed.item_code = %(item_code)s")
		detail_params["item_code"] = filters.get("item_code")

	details = frappe.db.sql(
		f"""
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
