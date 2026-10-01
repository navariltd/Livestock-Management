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


def get_data(filters: dict | None = None) -> list[dict]:
	filters = frappe._dict(filters or {})
	params = {
		key: filters.get(key) or None
		for key in [
			"company",
			"quality_inspection",
			"from_date",
			"to_date",
			"batch",
			"quality_inspection_template",
			"parameter",
		]
	}
	data = frappe.db.sql(
		"""
			WITH readings AS (
				SELECT
					qi.name AS quality_inspection,
					qi.report_date AS inspection_date,
					qi.batch_no AS batch,
					b.manufacturing_date,
					qi.sample_size,
					qi.quality_inspection_template,
					qir.idx,
					qir.specification AS parameter,
					qir.value, qir.reading_value, qir.min_value, qir.max_value,
					(COALESCE(qir.numeric, 0) = 0 OR (
						COALESCE(qir.min_value, 0) = 0 AND COALESCE(qir.max_value, 0) = 0
					)) AS value_based,
					(COALESCE(qir.reading_1, 0)
						+ COALESCE(qir.reading_2, 0)
						+ COALESCE(qir.reading_3, 0)
						+ COALESCE(qir.reading_4, 0)
						+ COALESCE(qir.reading_5, 0)
						+ COALESCE(qir.reading_6, 0)
						+ COALESCE(qir.reading_7, 0)
						+ COALESCE(qir.reading_8, 0)
						+ COALESCE(qir.reading_9, 0)
						+ COALESCE(qir.reading_10, 0)) AS reading_sum,
					(CASE WHEN qir.reading_1 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_2 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_3 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_4 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_5 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_6 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_7 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_8 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_9 IS NULL THEN 0 ELSE 1 END
						+ CASE WHEN qir.reading_10 IS NULL THEN 0 ELSE 1 END) AS reading_count
				FROM `tabQuality Inspection` qi
				INNER JOIN `tabQuality Inspection Reading` qir ON qir.parent = qi.name
				LEFT JOIN `tabBatch` b ON b.name = qi.batch_no
				WHERE qi.docstatus < 2
					AND (%(company)s IS NULL OR qi.company = %(company)s)
					AND (%(quality_inspection)s IS NULL OR qi.name = %(quality_inspection)s)
					AND (%(from_date)s IS NULL OR qi.report_date >= %(from_date)s)
					AND (%(to_date)s IS NULL OR qi.report_date <= %(to_date)s)
					AND (%(batch)s IS NULL OR qi.batch_no = %(batch)s)
					AND (%(quality_inspection_template)s IS NULL
						OR qi.quality_inspection_template = %(quality_inspection_template)s)
					AND (%(parameter)s IS NULL OR qir.specification = %(parameter)s)
			), calculated AS (
				SELECT readings.*,
					CASE WHEN value_based THEN CAST(NULLIF(value, '') AS DECIMAL(21, 9))
						ELSE (COALESCE(min_value, 0) + COALESCE(max_value, 0)) / 2
					END AS standard_reading,
					CASE WHEN value_based THEN CAST(NULLIF(reading_value, '') AS DECIMAL(21, 9))
						ELSE reading_sum / NULLIF(reading_count, 0)
					END AS actual_reading
				FROM readings
			)
			SELECT quality_inspection, inspection_date, batch, manufacturing_date,
				sample_size, quality_inspection_template, parameter,
				standard_reading, actual_reading,
				actual_reading - standard_reading AS variance
			FROM calculated
			ORDER BY inspection_date DESC, quality_inspection DESC, idx
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

	return data
