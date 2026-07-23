// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.query_reports["Mortality Report"] = {
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
			fieldname: "warehouse",
			label: __("Source Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
	],
};
