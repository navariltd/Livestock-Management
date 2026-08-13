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
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
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
						stock_entry_type: "Feeding",
					},
				};
			},
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
