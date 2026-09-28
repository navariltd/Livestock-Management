frappe.ui.form.on("Stock Entry", {
	async lvm_feed_formula(frm) {
		const feed_formula = frm.doc.lvm_feed_formula;

		frm.clear_table("items");

		if (!feed_formula) {
			frm.refresh_field("items");
			return;
		}

		const formula = await frappe.db.get_doc("Feed Formula", feed_formula);

		// Do not apply a response for a formula that is no longer selected.
		if (frm.doc.lvm_feed_formula !== feed_formula) {
			return;
		}

		for (const formula_item of formula.items || []) {
			const row = frm.add_child("items");

			// Run the Stock Entry Detail item triggers to populate item defaults.
			await frappe.model.set_value(row.doctype, row.name, "item_code", formula_item.item);
			await frappe.model.set_value(row.doctype, row.name, "qty", formula_item.quantity);

			if (formula_item.uom) {
				await frappe.model.set_value(row.doctype, row.name, "uom", formula_item.uom);
			}
		}

		frm.refresh_field("items");
	},
});
