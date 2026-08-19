// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.query_reports["Opportunity Forgone Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "selling_price_list",
			label: __("Selling Price List"),
			fieldtype: "Link",
			options: "Price List",
			reqd: 1,
		},
		{
			fieldname: "repack_entry",
			label: __("Repack Entry"),
			fieldtype: "Link",
			options: "Stock Entry",
			get_query: function () {
				return {
					filters: {
						stock_entry_type: "Capitalisation",
					},
				};
			},
		},
	],
	onload: function (report) {
		frappe.db.get_single_value("Selling Settings", "selling_price_list").then((price_list) => {
			if (price_list && !report.get_filter_value("selling_price_list")) {
				report.set_filter_value("selling_price_list", price_list);
			}
		});
	},
};
