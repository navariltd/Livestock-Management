frappe.ui.form.on("Batch", {
	refresh(frm) {
		update_batch_age(frm);
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
