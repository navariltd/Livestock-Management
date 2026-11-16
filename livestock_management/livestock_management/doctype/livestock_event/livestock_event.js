// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Livestock Event", {
	setup(frm) {
		frm.set_query("serial_no", () => ({
			filters: { item_code: frm.doc.animal || "" },
		}));
	},

	animal(frm) {
		if (frm.doc.serial_no) {
			frm.set_value("serial_no", null);
		}
	},
});
