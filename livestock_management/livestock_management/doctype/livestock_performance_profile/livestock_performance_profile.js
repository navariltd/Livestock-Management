frappe.ui.form.on("Livestock Performance Profile", {
	setup(frm) {
		frm.set_query("item", "egg_items", () => ({
			query: "livestock_management.livestock_management.stock_units.count_item_query",
			filters: { is_stock_item: 1 },
		}));
	},
});

// Age (Days) is the stored target age; Age (Weeks) is a convenience entry kept in sync.
const is_blank = (value) => value === null || value === undefined || value === "";

function sync_weeks_from_days(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (is_blank(row.age_days)) return;
	const weeks = flt(cint(row.age_days) / 7, 2);
	if (flt(row.age_weeks, 2) !== weeks) {
		frappe.model.set_value(cdt, cdn, "age_weeks", weeks);
	}
}

frappe.ui.form.on("Livestock Performance Target", {
	age_weeks(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (is_blank(row.age_weeks)) return;
		const days = Math.round(flt(row.age_weeks) * 7);
		if (cint(row.age_days) !== days || is_blank(row.age_days)) {
			frappe.model.set_value(cdt, cdn, "age_days", days);
		} else {
			// Days unchanged (e.g. 2.5 -> 18 days): still show the normalised weeks value.
			sync_weeks_from_days(cdt, cdn);
		}
	},
	age_days(frm, cdt, cdn) {
		sync_weeks_from_days(cdt, cdn);
	},
});
