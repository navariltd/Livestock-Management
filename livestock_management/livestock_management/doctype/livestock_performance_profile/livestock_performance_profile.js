frappe.ui.form.on("Livestock Performance Profile", {
	setup(frm) {
		frm.set_query("item", "egg_items", () => ({
			query: "livestock_management.livestock_management.stock_units.count_item_query",
			filters: { is_stock_item: 1 },
		}));
	},
});
