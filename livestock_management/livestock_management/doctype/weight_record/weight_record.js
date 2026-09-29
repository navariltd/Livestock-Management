// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Weight Record", {
	batch(frm) {
		set_age_from_batch(frm);
	},

	posting_date(frm) {
		set_age_from_batch(frm);
	},
});

async function set_age_from_batch(frm) {
	const batch = frm.doc.batch;
	const posting_date = frm.doc.posting_date;

	if (!batch || !posting_date) {
		await frm.set_value("age", null);
		return;
	}

	const { message } = await frappe.db.get_value("Batch", batch, "manufacturing_date");

	// Ignore a response if either source field changed while it was loading.
	if (frm.doc.batch !== batch || frm.doc.posting_date !== posting_date) {
		return;
	}

	const manufacturing_date = message?.manufacturing_date;
	const age = manufacturing_date
		? frappe.datetime.get_day_diff(posting_date, manufacturing_date)
		: null;
	await frm.set_value("age", age);
}
