# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, nowdate

READING_FIELDS = tuple(f"reading_{index}" for index in range(1, 11))


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})

	columns = get_columns()
	data = get_data(filters)
	print()

	return columns, data


def get_columns() -> list[dict]:
	return [
		{
			"label": _("Quality Inspection"),
			"fieldname": "quality_inspection",
			"fieldtype": "Link",
			"options": "Quality Inspection",
			"width": 180,
		},
		{
			"label": _("Date"),
			"fieldname": "inspection_date",
			"fieldtype": "Date",
			"width": 110,
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
			"label": _("Sample Size"),
			"fieldname": "sample_size",
			"fieldtype": "Float",
			"width": 110,
		},
		{
			"label": _("Quality Inspection Template"),
			"fieldname": "quality_inspection_template",
			"fieldtype": "Link",
			"options": "Quality Inspection Template",
			"width": 220,
		},
		{
			"label": _("Parameter"),
			"fieldname": "parameter",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Standard Reading"),
			"fieldname": "standard_reading",
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"label": _("Actual Reading"),
			"fieldname": "actual_reading",
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"label": _("Variance"),
			"fieldname": "variance",
			"fieldtype": "Float",
			"width": 120,
		},
	]


def get_conditions(filters: frappe._dict) -> tuple[list[str], dict]:
	conditions = ["qi.docstatus < 2"]
	params = {}

	if filters.get("company"):
		conditions.append("qi.company = %(company)s")
		params["company"] = filters.get("company")

	if filters.get("quality_inspection"):
		conditions.append("qi.name = %(quality_inspection)s")
		params["quality_inspection"] = filters.get("quality_inspection")

	if filters.get("from_date"):
		conditions.append("qi.report_date >= %(from_date)s")
		params["from_date"] = filters.get("from_date")

	if filters.get("to_date"):
		conditions.append("qi.report_date <= %(to_date)s")
		params["to_date"] = filters.get("to_date")

	if filters.get("batch"):
		conditions.append("qi.batch_no = %(batch)s")
		params["batch"] = filters.get("batch")

	if filters.get("quality_inspection_template"):
		conditions.append("qi.quality_inspection_template = %(quality_inspection_template)s")
		params["quality_inspection_template"] = filters.get("quality_inspection_template")

	if filters.get("parameter"):
		conditions.append("qir.specification = %(parameter)s")
		params["parameter"] = filters.get("parameter")

	return conditions, params


def get_data(filters: dict | None = None) -> list[dict]:
	filters = frappe._dict(filters or {})
	conditions, params = get_conditions(filters)
	reading_sum = " + ".join(f"COALESCE(qir.{field}, 0)" for field in READING_FIELDS)
	reading_count = " + ".join(f"CASE WHEN qir.{field} IS NULL THEN 0 ELSE 1 END" for field in READING_FIELDS)
	value_based_reading = """
		(
			COALESCE(qir.numeric, 0) = 0
			OR (
				COALESCE(qir.min_value, 0) = 0
				AND COALESCE(qir.max_value, 0) = 0
			)
		)
	"""
	standard_reading = f"""
		CASE
			WHEN {value_based_reading}
			THEN CAST(NULLIF(qir.value, '') AS DECIMAL(21, 9))
			ELSE (COALESCE(qir.min_value, 0) + COALESCE(qir.max_value, 0)) / 2
		END
	"""
	actual_reading = f"""
		CASE
			WHEN {value_based_reading}
			THEN CAST(NULLIF(qir.reading_value, '') AS DECIMAL(21, 9))
			WHEN ({reading_count}) = 0 THEN NULL
			ELSE ({reading_sum}) / ({reading_count})
		END
	"""

	print(f"\n\n\nDEBUG: standard_reading: {standard_reading}")

	data = frappe.db.sql(
		f"""
			SELECT
				qi.name AS quality_inspection,
				qi.report_date AS inspection_date,
				qi.batch_no AS batch,
				b.manufacturing_date,
				qi.sample_size,
				qi.quality_inspection_template,
				qir.specification AS parameter,
				({standard_reading}) AS standard_reading,
				({actual_reading}) AS actual_reading,
				CASE
					WHEN ({actual_reading}) IS NULL THEN NULL
					ELSE ({actual_reading}) - ({standard_reading})
				END AS variance
			FROM `tabQuality Inspection` qi
			INNER JOIN `tabQuality Inspection Reading` qir
				ON qir.parent = qi.name
			LEFT JOIN `tabBatch` b
				ON b.name = qi.batch_no
			WHERE {" AND ".join(conditions)}
			ORDER BY qi.report_date DESC, qi.name DESC, qir.idx
		""",
		params,
		as_dict=True,
	)

	today = nowdate()
	for row in data:
		manufacturing_date = row.get("manufacturing_date")
		if not manufacturing_date:
			continue

		age_in_days = date_diff(today, manufacturing_date)
		row["age_in_days"] = age_in_days
		row["age_in_weeks"] = age_in_days // 7

		print(
			f"DEBUG: Quality Inspection: {row['quality_inspection']}, Quality Inspection Template: {row['quality_inspection_template']}, Parameter: {row['parameter']}, Standard Reading: {row['standard_reading']}, Actual Reading: {row['actual_reading']}, Variance: {row['variance']}"
		)

	return data
