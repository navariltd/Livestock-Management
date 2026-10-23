frappe.query_reports["Batch Lifecycle Traceability"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "batch", label: __("Batch"), fieldtype: "Link", options: "Batch", reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company"), is_group: 0 },
			}),
		},
		{
			fieldname: "event_type",
			label: __("Event Type"),
			fieldtype: "Select",
			options: [
				"",
				"Receipt",
				"Birth",
				"Husbandry",
				"Weighing",
				"Treatment",
				"Feeding",
				"Produce collection",
				"Transfer",
				"Split",
				"Merge",
				"Batch replacement",
				"Reclassification / possible grading",
				"Ambiguous transformation",
				"Repack",
				"Mortality",
				"Culling",
				"Sale",
				"Customer return",
				"Supplier return",
				"Capitalisation",
				"Correction",
				"Stock issue",
			],
		},
		{
			fieldname: "include_related_batches",
			label: __("Include Related Batches"),
			fieldtype: "Check",
			default: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const fields = {
			parent_batches: "parent_batch_names",
			child_batches: "child_batch_names",
			related_batches: "related_batch_names",
		};
		const key = fields[column.fieldname];
		if (key && data && data[key]) {
			return data[key]
				.map(
					(name) =>
						`<a href="/app/batch/${encodeURIComponent(
							name
						)}">${frappe.utils.escape_html(name)}</a>`
				)
				.join(", ");
		}
		return default_formatter(value, row, column, data);
	},
};
