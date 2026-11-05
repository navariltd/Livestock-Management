// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Weight Record", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Fetch Previous Weight"), () =>
				open_previous_weight_dialog(frm)
			);
		}
	},

	batch(frm) {
		set_age_from_batch(frm);
	},

	posting_date(frm) {
		set_age_from_batch(frm);
	},
});

function open_previous_weight_dialog(frm) {
	if (!frm.doc.batch || !frm.doc.posting_date || !frm.doc.lvm_weight_uom) {
		frappe.msgprint(
			__(
				"Set the Batch, Posting Date, and Average Weight UOM before fetching a previous weight."
			)
		);
		return;
	}

	const context = {
		batch: frm.doc.batch,
		posting_date: frm.doc.posting_date,
		weight_uom: frm.doc.lvm_weight_uom,
		current_record: frm.is_new() ? null : frm.doc.name,
	};
	const dialog = new frappe.ui.Dialog({
		title: __("Fetch Previous Weight"),
		fields: [
			{
				fieldtype: "Link",
				fieldname: "weight_record",
				label: __("Previous Weight Record"),
				options: "Weight Record",
				reqd: 1,
				get_query: () => ({
					filters: {
						batch: context.batch,
						posting_date: ["<", context.posting_date],
						lvm_weight_uom: context.weight_uom,
						docstatus: ["<", 2],
						...(frm.is_new() ? {} : { name: ["!=", frm.doc.name] }),
					},
				}),
				onchange: () => show_previous_weight_preview(dialog, context),
			},
			{ fieldtype: "HTML", fieldname: "preview" },
		],
		primary_action_label: __("Use Actual Weight"),
		primary_action: async (values) => {
			if (
				frm.doc.batch !== context.batch ||
				frm.doc.posting_date !== context.posting_date ||
				frm.doc.lvm_weight_uom !== context.weight_uom
			) {
				frappe.msgprint(
					__("Batch, Posting Date, or Average Weight UOM changed. Reopen the picker.")
				);
				return;
			}

			const { message } = await frappe.call({
				method: "livestock_management.livestock_management.doctype.weight_record.weight_record.get_previous_weight_record",
				args: {
					weight_record: values.weight_record,
					...context,
				},
			});
			await frm.set_value("previous_weight", message.actual_weight);
			dialog.hide();
		},
	});
	dialog.show();
}

async function show_previous_weight_preview(dialog, context) {
	const weight_record = dialog.get_value("weight_record");
	const preview = dialog.fields_dict.preview.$wrapper;
	if (!weight_record) {
		preview.empty();
		return;
	}

	const { message } = await frappe.call({
		method: "livestock_management.livestock_management.doctype.weight_record.weight_record.get_previous_weight_record",
		args: {
			weight_record,
			current_record: context.current_record,
			batch: context.batch,
			posting_date: context.posting_date,
			weight_uom: context.weight_uom,
		},
	});
	const format = (value) => frappe.utils.escape_html(String(value ?? "—"));
	preview.html(
		`<div class="text-muted">${__("Date")}: ${format(message.posting_date)} &nbsp; · &nbsp; ` +
			`${__("Age")}: ${format(message.age)} &nbsp; · &nbsp; ` +
			`${__("Actual Weight")}: ${format(message.actual_weight)} ${format(
				message.weight_uom
			)}</div>`
	);
}

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
