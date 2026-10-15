# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate, nowtime

from livestock_management.livestock_management.overrides.stock_entry import (
	create_repack_entry,
	get_capitalisation_target,
	get_material_issue_costs,
)


class VeterinaryDiagnosis(Document):
	def before_submit(self):
		if self.status != "Completed":
			frappe.throw(_("Only a Completed veterinary diagnosis can be submitted."))
		if not self.get("treatment_plans"):
			frappe.throw(_("Add at least one medicine to the Treatment Plans table."))
		self.validate_treatment_stock()
		self.validate_purchase_invoice_costs()
		if self.to_capitalize:
			get_capitalisation_target(
				self.company,
				self.get("batch"),
				self.get("serial_no"),
				self.get("capitalisation_warehouse"),
			)

	def validate(self):
		"""Auto-set the end date to the current date if status is 'Completed' and end date is not provided."""
		self.company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		if self.status == "Completed" and not self.end_date:
			self.end_date = nowdate()

		# Set the start and end dates on the treatment_plans table rows based on self.start_date and self.end_date
		for treatment_plan in self.treatment_plans:
			if not treatment_plan.start_date and self.start_date:
				treatment_plan.start_date = self.start_date
			if not treatment_plan.end_date and self.end_date:
				treatment_plan.end_date = self.end_date

	def validate_treatment_stock(self):
		for row in self.treatment_plans:
			item = frappe.get_cached_doc("Item", row.item)
			if not item.is_stock_item or item.disabled:
				frappe.throw(_("Row {0}: Select an enabled stock Item for the medicine.").format(row.idx))
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: Medicine stock quantity must be greater than zero.").format(row.idx))
			if not row.warehouse:
				frappe.throw(_("Row {0}: Select the medicine's source warehouse.").format(row.idx))
			warehouse = frappe.get_doc("Warehouse", row.warehouse)
			if warehouse.company != self.company or warehouse.is_group:
				frappe.throw(
					_("Row {0}: Select a non-group warehouse in the diagnosis company.").format(row.idx)
				)
			if item.has_batch_no:
				if not row.batch_no:
					frappe.throw(_("Row {0}: A Batch is required for this medicine.").format(row.idx))
				batch = frappe.get_doc("Batch", row.batch_no)
				if batch.item != row.item or batch.disabled:
					frappe.throw(
						_("Row {0}: Select an enabled Batch belonging to the medicine Item.").format(row.idx)
					)
			if item.has_serial_no and not row.serial_no:
				frappe.throw(_("Row {0}: Serial numbers are required for this medicine.").format(row.idx))
			# ERPNext checks quantity, availability and serial/batch consistency when submitting the issue.

	def validate_expense_account(self, account_name):
		if not account_name:
			frappe.throw(
				_("Set the Treatment Stock Entry Difference Account for Company {0}.").format(self.company)
			)
		account = frappe.get_doc("Account", account_name)
		currency = frappe.get_cached_value("Company", self.company, "default_currency")
		if (
			account.company != self.company
			or account.is_group
			or account.disabled
			or account.root_type != "Expense"
			or (account.account_currency and account.account_currency != currency)
		):
			frappe.throw(
				_(
					"Account {0} must be an enabled expense ledger in the diagnosis company and currency."
				).format(account_name)
			)

	def validate_purchase_invoice_costs(self):
		"""Allocate only invoiced non-stock expenses, in company currency, without reusing costs."""
		requested = defaultdict(float)
		precision = self.precision("total_medical_cost")
		for row in self.get("purchase_invoices") or []:
			if not row.purchase_invoice or flt(row.cost) <= 0:
				frappe.throw(
					_(
						"Invoice row {0}: Select a Purchase Invoice and enter a positive allocated cost."
					).format(row.idx)
				)
			self.validate_expense_account(row.expense_account)
			key = (row.purchase_invoice, row.expense_account)
			requested[key] += flt(row.cost)

		# Lock in a stable order so concurrent submissions cannot capitalise the same invoice costs twice.
		for invoice_name in sorted({key[0] for key in requested}):
			invoice = frappe.get_doc("Purchase Invoice", invoice_name, for_update=True)
			invoice.check_permission("read")
			if invoice.docstatus != 1 or invoice.company != self.company or invoice.is_return:
				frappe.throw(
					_(
						"Purchase Invoice {0} must be submitted, non-return, and in the diagnosis company."
					).format(invoice_name)
				)
			eligible = defaultdict(float)
			for line in invoice.items:
				item = frappe.get_cached_doc("Item", line.item_code) if line.item_code else None
				if (item and (item.is_stock_item or item.is_fixed_asset)) or line.get(
					"enable_deferred_expense"
				):
					continue
				eligible[line.expense_account] += flt(line.base_net_amount)

			for (name, account), amount in requested.items():
				if name != invoice_name:
					continue
				allocated = self.get_allocated_invoice_cost(name, account) if self.to_capitalize else 0
				if flt(amount + allocated - eligible[account], precision) > 0:
					frappe.throw(
						_(
							"Purchase Invoice {0}: Allocated costs exceed the available non-stock net expense for account {1}. Medicine purchase costs already included in stock valuation cannot be added again."
						).format(name, account)
					)

	def get_allocated_invoice_cost(self, invoice, account):
		allocation = frappe.qb.DocType("Vet Diagnosis Purchase Invoices")
		diagnosis = frappe.qb.DocType("Veterinary Diagnosis")
		result = (
			frappe.qb.from_(allocation)
			.inner_join(diagnosis)
			.on(allocation.parent == diagnosis.name)
			.select(allocation.cost)
			.where(
				(allocation.purchase_invoice == invoice)
				& (allocation.expense_account == account)
				& (allocation.parenttype == "Veterinary Diagnosis")
				& (diagnosis.docstatus == 1)
				& (diagnosis.to_capitalize == 1)
				& (diagnosis.name != self.name)
			)
			.for_update()
		).run()
		return sum(flt(row[0]) for row in result)

	def get_generated_entry(self, entry_type):
		name = frappe.db.get_value(
			"Stock Entry",
			{
				"lvm_veterinary_diagnosis": self.name,
				"stock_entry_type": entry_type,
				"docstatus": ["!=", 2],
			},
			"name",
		)
		if not name:
			return None
		entry = frappe.get_doc("Stock Entry", name)
		if entry.docstatus != 1:
			frappe.throw(
				_("Submit or remove the existing draft {0} Stock Entry {1} before proceeding.").format(
					entry_type, name
				)
			)
		return entry

	def on_submit(self):
		# Normal Document submission already locks this record; keep direct/retried calls idempotent too.
		frappe.db.get_value(self.doctype, self.name, "name", for_update=True)
		medical_entry = self.get_generated_entry("Medical") or self.create_medical_entry()
		invoice_costs = [
			{
				"description": _("Medical expense allocated from Purchase Invoice {0}").format(
					row.purchase_invoice
				),
				"amount": flt(row.cost),
				"expense_account": row.expense_account,
			}
			for row in self.get("purchase_invoices") or []
		]
		self.db_set("medical_stock_entry", medical_entry.name, update_modified=False)
		self.db_set(
			"total_medical_cost",
			flt(
				flt(medical_entry.total_outgoing_value) + sum(row["amount"] for row in invoice_costs),
				self.precision("total_medical_cost"),
			),
			update_modified=False,
		)
		if self.to_capitalize:
			repack = self.get_generated_entry("Capitalisation") or create_repack_entry(
				medical_entry,
				serial_no=self.get("serial_no"),
				warehouse=self.get("capitalisation_warehouse"),
				additional_costs=get_material_issue_costs(medical_entry) + invoice_costs,
			)
			self.db_set("capitalisation_stock_entry", repack.name, update_modified=False)

	def create_medical_entry(self):
		# Use company-specific account to avoid cross-company accounting issues in multi-company setups.
		account = frappe.db.get_value("Company", self.company, "lvm_treatment_stock_entry_difference_account")
		self.validate_expense_account(account)
		entry = frappe.new_doc("Stock Entry")
		entry.stock_entry_type = "Medical"
		entry.purpose = "Material Issue"
		entry.company = self.company
		entry.set_posting_time = 1
		entry.posting_date = self.posting_date
		entry.posting_time = nowtime()
		entry.lvm_batch = self.get("batch")
		entry.lvm_treatment_type = self.get("treatment_type")
		entry.lvm_veterinary_diagnosis = self.name
		for row in self.treatment_plans:
			item = frappe.get_cached_doc("Item", row.item)
			entry.append(
				"items",
				{
					"item_code": row.item,
					"qty": flt(row.qty),
					"uom": item.stock_uom,
					"stock_uom": item.stock_uom,
					"conversion_factor": 1,
					"s_warehouse": row.warehouse,
					"expense_account": account,
					"batch_no": row.batch_no if item.has_batch_no else None,
					"serial_no": row.serial_no if item.has_serial_no else None,
					"use_serial_batch_fields": 1,
				},
			)
		entry.insert()
		entry.submit()
		entry.reload()
		return entry

	def on_cancel(self):
		# Reverse valuation before reversing consumption; never cancel the linked Purchase Invoices.
		for entry_type in ("Capitalisation", "Medical"):
			entry = self.get_generated_entry(entry_type)
			if entry:
				entry.cancel()

	def before_cancel(self):
		# Coordinate releasing allocations with other diagnoses submitting against the same invoices.
		for invoice in sorted({row.purchase_invoice for row in self.get("purchase_invoices") or []}):
			frappe.db.get_value("Purchase Invoice", invoice, "name", for_update=True)
