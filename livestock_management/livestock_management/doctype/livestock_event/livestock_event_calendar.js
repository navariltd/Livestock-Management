frappe.views.calendar["Livestock Event"] = {
	fields: ["name", "husbandry", "starts_on", "ends_on", "all_day"],
	field_map: {
		start: "starts_on",
		end: "ends_on",
		id: "name",
		title: "husbandry",
		allDay: "all_day",
	},
	filters: [
		{
			fieldtype: "Link",
			fieldname: "husbandry",
			options: "Husbandry Practice",
			label: __("Husbandry Practice"),
		},
		{
			fieldtype: "Link",
			fieldname: "serial_no",
			options: "Serial No",
			label: __("Animal Serial No"),
		},
		{
			fieldtype: "Link",
			fieldname: "batch",
			options: "Batch",
			label: __("Batch"),
		},
	],
	get_events_method:
		"livestock_management.livestock_management.doctype.livestock_event.livestock_event.get_events",
};
