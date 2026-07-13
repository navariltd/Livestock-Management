// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.query_reports["Livestock Inspection Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "quality_inspection",
			label: __("Quality Inspection"),
			fieldtype: "Link",
			options: "Quality Inspection",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "batch",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch",
		},
		{
			fieldname: "quality_inspection_template",
			label: __("Quality Inspection Template"),
			fieldtype: "Link",
			options: "Quality Inspection Template",
		},
		{
			fieldname: "parameter",
			label: __("Parameter"),
			fieldtype: "Data",
		},
	],
};
