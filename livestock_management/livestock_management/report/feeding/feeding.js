// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.query_reports["Feeding"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
		},
		{
			fieldname: "posting_date",
			label: __("Posting Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "batch",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch",
		},
		{
			fieldname: "warehouse",
			label: __("Source Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "item_code",
			label: __("Item Code"),
			fieldtype: "Link",
			options: "Item",
		},
	],
};
