frappe.ui.form.on("Livestock Performance Alert Rule", {
	setup(frm) {
		frm.set_query("warehouse", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
		frm.set_query("item_code", () => ({
			filters: { is_stock_item: 1, has_batch_no: 1, stock_uom: ["in", ["Nos", "Unit"]] },
		}));
		frm.set_query("responsible_user", () => ({
			filters: { enabled: 1, user_type: "System User" },
		}));
	},
});
