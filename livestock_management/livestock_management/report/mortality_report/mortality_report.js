// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.query_reports["Mortality Report"] = {
	tree: true,
	name_field: "row_index",
	parent_field: "parent_row_index",
	initial_depth: 1,
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
			fieldname: "stock_entry",
			label: __("Stock Entry"),
			fieldtype: "Link",
			options: "Stock Entry",
			get_query: function () {
				return {
					filters: {
						docstatus: 1,
						stock_entry_type: "Mortality",
					},
				};
			},
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
