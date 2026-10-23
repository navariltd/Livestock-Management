frappe.ui.form.on("Livestock Performance Profile", {
	setup(frm) {
		frm.set_query("item", "egg_items", () => ({
			filters: { is_stock_item: 1, stock_uom: ["in", ["Nos", "Unit"]] },
		}));
	},
});
