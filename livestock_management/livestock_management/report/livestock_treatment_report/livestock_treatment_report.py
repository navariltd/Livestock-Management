# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, nowdate


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})

	return get_columns(), get_data(filters)


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
			"label": _("Livestock Batch"),
			"fieldname": "livestock_batch",
			"fieldtype": "Link",
			"options": "Batch",
			"width": 140,
		},
		{
			"label": _("Age in Days"),
			"fieldname": "age_in_days",
			"fieldtype": "Int",
			"width": 105,
		},
		{
			"label": _("Age in Weeks"),
			"fieldname": "age_in_weeks",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": _("Treatment Type"),
			"fieldname": "treatment_type",
			"fieldtype": "Link",
			"options": "Treatment Type",
			"width": 150,
		},
		{
			"label": _("Vet Name"),
			"fieldname": "vet_name",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Vet Phone Number"),
			"fieldname": "vet_phone_number",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Source Warehouse"),
			"fieldname": "s_warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{
			"label": _("Quantity"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 90,
		},
		{
			"label": _("Valuation Rate"),
			"fieldname": "valuation_rate",
			"fieldtype": "Currency",
			"width": 125,
		},
		{
			"label": _("Total Cost"),
			"fieldname": "total_cost",
			"fieldtype": "Currency",
			"width": 125,
		},
	]


def get_data(filters: dict | None = None) -> list[dict]:
	filters = frappe._dict(filters or {})
	params = {
		key: filters.get(key) or None
		for key in [
			"company",
			"stock_entry",
			"batch",
			"treatment_type",
			"warehouse",
			"item_code",
			"from_date",
			"to_date",
		]
	}

	details = frappe.db.sql(
		"""
			SELECT
				se.posting_date,
				se.posting_time,
				se.name AS stock_entry,
				se.lvm_batch AS livestock_batch,
				se.lvm_treatment_type AS treatment_type,
				se.lvm_vet_name AS vet_name,
				se.lvm_vet_phone_number AS vet_phone_number,
				b.manufacturing_date,
				sed.idx,
				sed.item_code,
				sed.item_name,
				sed.s_warehouse,
				sed.qty,
				sed.uom,
				sed.valuation_rate,
				(sed.qty * sed.valuation_rate) AS total_cost
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed
				ON sed.parent = se.name
			LEFT JOIN `tabBatch` b
				ON b.name = se.lvm_batch
			WHERE se.docstatus = 1 AND se.stock_entry_type = 'Treatment' AND sed.s_warehouse IS NOT NULL
				AND (%(company)s IS NULL OR se.company = %(company)s)
				AND (%(stock_entry)s IS NULL OR se.name = %(stock_entry)s)
				AND (%(batch)s IS NULL OR se.lvm_batch = %(batch)s)
				AND (%(treatment_type)s IS NULL OR se.lvm_treatment_type = %(treatment_type)s)
				AND (%(warehouse)s IS NULL OR sed.s_warehouse = %(warehouse)s)
				AND (%(item_code)s IS NULL OR sed.item_code = %(item_code)s)
				AND (%(from_date)s IS NULL OR se.posting_date >= %(from_date)s)
				AND (%(to_date)s IS NULL OR se.posting_date <= %(to_date)s)
			ORDER BY
				se.posting_date DESC,
				se.posting_time DESC,
				se.name DESC,
				sed.idx
		""",
		params,
		as_dict=True,
	)

	return build_tree_rows(details)


def build_tree_rows(details: list[dict]) -> list[dict]:
	"""Build one treatment header followed by its indented stock item rows."""
	if not details:
		return []

	stock_entries = {}
	for detail in details:
		stock_entries.setdefault(detail.stock_entry, []).append(detail)

	data = []
	today = nowdate()
	for stock_entry_index, entry_details in enumerate(stock_entries.values(), start=1):
		first_detail = entry_details[0]
		parent_row_index = str(stock_entry_index)
		age_in_days = None
		age_in_weeks = None

		if first_detail.manufacturing_date:
			age_in_days = date_diff(today, first_detail.manufacturing_date)
			age_in_weeks = age_in_days // 7

		data.append(
			{
				"row_index": parent_row_index,
				"posting_date": first_detail.posting_date,
				"stock_entry": first_detail.stock_entry,
				"livestock_batch": first_detail.livestock_batch,
				"age_in_days": age_in_days,
				"age_in_weeks": age_in_weeks,
				"treatment_type": first_detail.treatment_type,
				"vet_name": first_detail.vet_name,
				"vet_phone_number": first_detail.vet_phone_number,
				"total_cost": sum(detail.total_cost or 0 for detail in entry_details),
				"indent": 0,
				"is_group": 1,
			}
		)

		for detail_index, detail in enumerate(entry_details, start=1):
			data.append(
				{
					"row_index": f"{parent_row_index}.{detail_index}",
					"parent_row_index": parent_row_index,
					"item_code": detail.item_code,
					"item_name": detail.item_name,
					"s_warehouse": detail.s_warehouse,
					"qty": detail.qty,
					"uom": detail.uom,
					"valuation_rate": detail.valuation_rate,
					"total_cost": detail.total_cost,
					"indent": 1,
				}
			)

	return data
