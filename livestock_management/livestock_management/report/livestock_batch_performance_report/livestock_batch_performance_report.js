// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.query_reports["Livestock Batch Performance report"] = {
	tree: true,
	name_field: "row_id",
	parent_field: "parent_row_id",
	initial_depth: 2,
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
			reqd: 1,
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "item_code",
			label: __("Livestock Item"),
			fieldtype: "Link",
			options: "Item",
			description: __("Leave blank to show all accessible batch-tracked livestock Items."),
			get_query: () => ({ filters: { has_batch_no: 1, is_stock_item: 1 } }),
			on_change: () => {
				frappe.query_report.set_filter_value("batch", "");
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "batch",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch",
			get_query: () => {
				const item = frappe.query_report.get_filter_value("item_code");
				return { filters: item ? { item } : {} };
			},
		},
		{
			fieldname: "warehouse",
			label: __("Livestock House / Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company"), is_group: 0 },
			}),
		},
	],
};
