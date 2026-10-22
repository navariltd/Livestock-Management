frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Daily Population"] = {
	method: "livestock_management.livestock_management.dashboard_chart_source.daily_population.daily_population.get",
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
			fieldname: "item_code",
			label: __("Livestock Item"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({
				filters: { is_stock_item: 1, has_batch_no: 1, stock_uom: ["in", ["Nos", "Unit"]] },
			}),
		},
		{
			fieldname: "batch",
			label: __("Batch"),
			fieldtype: "Link",
			options: "Batch",
			get_query: () => ({ filters: { lvm_is_livestock_item: 1 } }),
		},
		{
			fieldname: "warehouse",
			label: __("Livestock House / Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({ filters: { is_group: 0 } }),
		},
	],
};
