// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Offspring", {
	async item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (!row.item) {
			await frappe.model.set_value(cdt, cdn, {
				has_serial_no: 0,
				create_serial_number: 0,
				requested_serial_no: null,
			});
			return;
		}

		const { message } = await frappe.db.get_value("Item", row.item, [
			"has_serial_no",
			"serial_no_series",
		]);

		await frappe.model.set_value(cdt, cdn, "has_serial_no", message.has_serial_no || 0);

		if (message.has_serial_no) {
			await frappe.model.set_value(cdt, cdn, "create_serial_number", 1);

			if (!message.serial_no_series) {
				frappe.msgprint(
					__("Enter a new Serial Number for offspring item {0}.", [row.item])
				);
			}
		}
	},
});
