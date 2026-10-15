import frappe
from erpnext.stock.doctype.batch.batch import get_batch_qty
from frappe import _
from frappe.utils import flt

STOCK_ENTRY_DIFFERENCE_ACCOUNT_FIELDS = {
	"Feeding": "lvm_feeding_stock_entry_difference_account",
	"Treatment": "lvm_treatment_stock_entry_difference_account",
	"Medical": "lvm_treatment_stock_entry_difference_account",
	"Capitalisation": "lvm_capitalisation_stock_entry_difference_account",
	"Egg Production": "lvm_egg_production_stock_entry_difference_account",
	"Mortality": "lvm_mortality_stock_entry_difference_account",
}

CAPITALIZABLE_STOCK_ENTRY_TYPES = {"Feeding", "Treatment"}


def before_save_livestock_entry(doc, method):
	"""
	Set Stock Entry Detail difference accounts from the Stock Entry company.
	"""
	company_field = STOCK_ENTRY_DIFFERENCE_ACCOUNT_FIELDS.get(doc.stock_entry_type)
	if not company_field:
		return

	expense_account = frappe.db.get_value("Company", doc.company, company_field)
	if not expense_account:
		return

	for item in doc.items:
		item.expense_account = expense_account


def on_submit_livestock_entry(doc, method):
	"""
	Handle qualifying livestock Stock Entry submissions,
	creating repack entries for active batch capitalisation.
	"""
	if doc.purpose == "Material Issue" and doc.stock_entry_type in CAPITALIZABLE_STOCK_ENTRY_TYPES:
		if not doc.items or not doc.get("lvm_batch"):
			return

		batch = frappe.get_doc("Batch", doc.lvm_batch)
		if batch.get("lvm_capitalisation_status") == "Active":
			create_repack_entry(doc)


def get_capitalisation_target(company, batch_no=None, serial_no=None, warehouse=None):
	"""Resolve the existing livestock stock to revalue, never the medicine's stock."""
	if serial_no:
		serial = frappe.get_doc("Serial No", serial_no)
		if batch_no and batch_no != serial.batch_no:
			frappe.throw(_("The livestock Batch must match the selected Serial No's Batch."))
		if serial.company != company or not serial.warehouse:
			frappe.throw(_("The livestock Serial No must be in stock in the selected company."))
		if warehouse and warehouse != serial.warehouse:
			frappe.throw(_("The capitalisation warehouse must match the Serial No's current warehouse."))
		warehouse = serial.warehouse
		batch_no = serial.batch_no
		item_code = serial.item_code
		qty = 1
	elif batch_no:
		batch = frappe.get_doc("Batch", batch_no)
		if batch.disabled:
			frappe.throw(_("Select an enabled livestock Batch."))
		warehouse = warehouse or batch.get("lvm_location")
		item_code = batch.item
		qty = None
	else:
		frappe.throw(_("Select a livestock Batch or Serial No to capitalise medical costs."))

	if not warehouse:
		frappe.throw(_("Select a capitalisation warehouse or set the livestock Batch's Location."))
	warehouse_doc = frappe.get_doc("Warehouse", warehouse)
	if warehouse_doc.company != company or warehouse_doc.is_group:
		frappe.throw(_("The capitalisation warehouse must be a non-group warehouse in the selected company."))

	item = frappe.get_cached_doc("Item", item_code)
	if not item.is_stock_item or item.disabled:
		frappe.throw(_("The livestock must be an enabled stock Item."))
	if item.has_serial_no and not serial_no:
		frappe.throw(_("Select a livestock Serial No when capitalising a serial-tracked Item."))
	if item.has_batch_no:
		if not batch_no:
			frappe.throw(_("The livestock Item requires a Batch."))
		batch = frappe.get_doc("Batch", batch_no)
		if batch.item != item_code or batch.disabled:
			frappe.throw(_("Select an enabled Batch belonging to the livestock Item."))

	return frappe._dict(
		item_code=item_code,
		warehouse=warehouse,
		batch_no=batch_no if item.has_batch_no else None,
		serial_no=serial_no,
		qty=qty,
	)


def get_material_issue_costs(source_doc):
	"""Keep the actual issued valuation grouped by the accounts originally expensed."""
	amounts = {}
	for row in source_doc.items:
		amounts[row.expense_account] = amounts.get(row.expense_account, 0) + flt(row.amount)
	return [
		{
			"description": _("Capitalising {0} costs from {1}").format(
				source_doc.stock_entry_type, source_doc.name
			),
			"amount": amount,
			"expense_account": account,
		}
		for account, amount in amounts.items()
		if amount
	]


def create_repack_entry(source_doc, item_row=None, *, serial_no=None, warehouse=None, additional_costs=None):
	"""
	Capitalise costs onto existing livestock, letting ERPNext calculate its current valuation.

	item_row is retained for compatibility; its medicine valuation must not value the livestock.
	"""
	target = get_capitalisation_target(source_doc.company, source_doc.get("lvm_batch"), serial_no, warehouse)
	if target.qty is None:
		target.qty = flt(
			get_batch_qty(
				batch_no=target.batch_no,
				warehouse=target.warehouse,
				item_code=target.item_code,
				posting_date=source_doc.posting_date,
				posting_time=source_doc.posting_time,
			)
		)
		if target.qty <= 0:
			frappe.throw(_("The livestock Batch has no available stock in the capitalisation warehouse."))

	repack_doc = frappe.new_doc("Stock Entry")
	repack_doc.stock_entry_type = "Capitalisation"
	repack_doc.purpose = "Repack"
	repack_doc.company = source_doc.company
	repack_doc.lvm_source_material_issue = source_doc.name
	repack_doc.lvm_batch = target.batch_no
	repack_doc.lvm_veterinary_diagnosis = source_doc.get("lvm_veterinary_diagnosis")

	# Explicitly copy posting details and ensure posting time can be manually set
	repack_doc.set_posting_time = 1
	repack_doc.posting_date = source_doc.posting_date
	repack_doc.posting_time = source_doc.posting_time

	for cost in additional_costs if additional_costs is not None else get_material_issue_costs(source_doc):
		repack_doc.append("additional_costs", cost)

	# Consume and receive the same livestock; ERPNext adds the costs to its incoming valuation.
	# Row 1: Source (Raw Material)
	repack_doc.append(
		"items",
		{
			"item_code": target.item_code,
			"batch_no": target.batch_no,
			"serial_no": target.serial_no,
			"s_warehouse": target.warehouse,
			"qty": target.qty,
			"use_serial_batch_fields": 1,
		},
	)

	# Row 2: Target (Finished Good)
	repack_doc.append(
		"items",
		{
			"item_code": target.item_code,
			"batch_no": target.batch_no,
			"serial_no": target.serial_no,
			"t_warehouse": target.warehouse,
			"qty": target.qty,
			"is_finished_item": 1,
			"use_serial_batch_fields": 1,
		},
	)

	repack_doc.insert()
	repack_doc.submit()
	return repack_doc
