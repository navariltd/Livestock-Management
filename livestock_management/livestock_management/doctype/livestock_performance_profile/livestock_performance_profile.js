frappe.ui.form.on("Livestock Performance Profile", {
	setup(frm) {
		frm.set_query("item", "egg_items", () => ({
			query: "livestock_management.livestock_management.stock_units.count_item_query",
			filters: { is_stock_item: 1 },
		}));
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.fields_dict.targets.grid.add_custom_button(__("Fill Mortality from Cumulative"), () =>
			open_cumulative_mortality_dialog(frm)
		);
	},
});

const PROFILE_METHOD =
	"livestock_management.livestock_management.doctype.livestock_performance_profile.livestock_performance_profile";

async function open_cumulative_mortality_dialog(frm) {
	const targets = (frm.doc.targets || []).filter((row) => !is_blank(row.age_days));
	if (!targets.length) {
		frappe.msgprint(__("Add target rows with Age (Days) first."));
		return;
	}
	// Pre-fill with the cumulative figures implied by the current daily rates, so re-opening edits them.
	const { message: current = [] } = await frappe.call({
		method: `${PROFILE_METHOD}.cumulative_mortality`,
		args: {
			rows: targets.map((row) => ({
				age_days: row.age_days,
				mortality_percent: row.mortality_percent,
			})),
		},
	});
	const dialog = new frappe.ui.Dialog({
		title: __("Fill Mortality from Cumulative"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"Enter cumulative mortality as % of placed animals dead by the end of each age, e.g. from a breed guide. Daily rates are filled into every target row up to the last age entered; between two entries the daily rate is held constant. Rows after the last entry are left unchanged."
				)}</p>`,
			},
			{
				fieldname: "points",
				fieldtype: "Table",
				label: __("Cumulative Mortality"),
				in_place_edit: true,
				data: current,
				fields: [
					{
						fieldname: "age_days",
						fieldtype: "Int",
						label: __("Age (Days)"),
						in_list_view: 1,
						reqd: 1,
					},
					{
						fieldname: "cumulative_percent",
						fieldtype: "Float",
						label: __("Cumulative Mortality (%)"),
						precision: 4,
						in_list_view: 1,
						reqd: 1,
					},
				],
			},
		],
		primary_action_label: __("Fill Daily Mortality"),
		async primary_action({ points }) {
			if (!points || !points.length) {
				frappe.msgprint(__("Enter at least one cumulative mortality figure."));
				return;
			}
			const { message: rates } = await frappe.call({
				method: `${PROFILE_METHOD}.convert_cumulative_mortality`,
				args: {
					ages: targets.map((row) => cint(row.age_days)),
					points: points.map(({ age_days, cumulative_percent }) => ({
						age_days,
						cumulative_percent,
					})),
				},
			});
			let updated = 0;
			for (const row of targets) {
				const rate = rates[String(cint(row.age_days))];
				if (rate === undefined) continue;
				frappe.model.set_value(row.doctype, row.name, "mortality_percent", String(rate));
				updated++;
			}
			frm.refresh_field("targets");
			dialog.hide();
			frappe.show_alert({
				message: __("Daily mortality filled on {0} target rows.", [updated]),
				indicator: "green",
			});
		},
	});
	dialog.show();
}

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
