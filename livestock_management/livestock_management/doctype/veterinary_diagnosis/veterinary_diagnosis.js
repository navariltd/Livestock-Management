// Copyright (c) 2026, Navari Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Veterinary Diagnosis", {
	setup(frm) {
		const warehouse_filters = () => ({ company: frm.doc.company, is_group: 0 });
		frm.set_query("capitalisation_warehouse", () => ({ filters: warehouse_filters() }));
		frm.set_query("warehouse", "treatment_plans", () => ({ filters: warehouse_filters() }));
		frm.set_query("item", "treatment_plans", () => ({
			filters: { is_stock_item: 1, disabled: 0 },
		}));
		frm.set_query("batch_no", "treatment_plans", (doc, cdt, cdn) => ({
			filters: { item: locals[cdt][cdn].item, disabled: 0 },
		}));
		frm.set_query("purchase_invoice", "purchase_invoices", () => ({
			filters: { company: frm.doc.company, docstatus: 1, is_return: 0 },
		}));
		frm.set_query("expense_account", "purchase_invoices", () => ({
			filters: {
				company: frm.doc.company,
				root_type: "Expense",
				is_group: 0,
				disabled: 0,
			},
		}));
	},
});

frappe.ui.form.on("Treatment Plan", {
	item(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, { batch_no: "", serial_no: "" });
	},
});
