frappe.ui.form.on("Batch", {
	setup(frm) {
		frm.set_query("lvm_performance_profile", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		update_batch_age(frm);
		if (!frm.is_new() && frappe.model.can_read("Stock Ledger Entry")) {
			frm.add_custom_button(__("Lifecycle Traceability"), () => {
				frappe.set_route("query-report", "Batch Lifecycle Traceability", {
					batch: frm.doc.name,
					company: frappe.defaults.get_user_default("Company"),
					to_date: frappe.datetime.get_today(),
					include_related_batches: 1,
				});
			});
		}
	},

	manufacturing_date(frm) {
		update_batch_age(frm);
	},
});

function update_batch_age(frm) {
	let days = null;
	let weeks = null;

	if (frm.doc.manufacturing_date) {
		days = frappe.datetime.get_diff(frappe.datetime.get_today(), frm.doc.manufacturing_date);
		weeks = Math.floor(days / 7);
	}

	// Virtual display values should not mark the Batch as unsaved.
	frm.doc.lvm_age_in_days = days;
	frm.doc.lvm_age_weeks = weeks;
	frm.refresh_field("lvm_age_in_days");
	frm.refresh_field("lvm_age_weeks");
}
