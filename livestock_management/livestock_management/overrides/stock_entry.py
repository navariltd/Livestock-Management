import frappe

STOCK_ENTRY_DIFFERENCE_ACCOUNT_FIELDS = {
	"Feeding": "feeding_stock_entry_difference_account",
	"Treatment": "treatment_stock_entry_difference_account",
	"Capitalisation": "capitalisation_stock_entry_difference_account",
	"Egg Production": "egg_production_stock_entry_difference_account",
	"Mortality": "mortality_stock_entry_difference_account",
}


def before_save_livestock_entry(doc, method):
	"""
	Set Stock Entry Detail difference accounts from Livestock Management Settings.
	"""
	settings_field = STOCK_ENTRY_DIFFERENCE_ACCOUNT_FIELDS.get(doc.stock_entry_type)
	if not settings_field:
		return

	expense_account = frappe.db.get_single_value("Livestock Management Settings", settings_field)
	if not expense_account:
		return

	for item in doc.items:
		item.expense_account = expense_account


def on_submit_livestock_entry(doc, method):
	"""
	Handle Stock Entry submissions for Feeding and Treatment,
	creating repack entries for active batch capitalisation.
	"""
	if doc.purpose == "Material Issue" and doc.stock_entry_type in ["Feeding", "Treatment"]:
		if not doc.items:
			return

		for item in doc.items:
			batch = frappe.get_doc("Batch", doc.lvm_batch)
			if batch.get("lvm_capitalisation_status") == "Active":
				create_repack_entry(doc, item)
				break


def create_repack_entry(source_doc, item_row):
	"""
	Create and submit a Capitalisation(repack) Stock Entry for a qualifying feed or treatment batch.
	"""
	repack_doc = frappe.new_doc("Stock Entry")
	repack_doc.stock_entry_type = "Capitalisation"
	repack_doc.purpose = "Material Transfer for Manufacture"
	repack_doc.company = source_doc.company
	repack_doc.posting_date = source_doc.posting_date

	# 1. Fetch Expense Account from the first item of the source document
	first_item = source_doc.items[0]
	expense_account = first_item.get("expense_account")

	# 2. Get batch location for warehouse settings
	batch_doc = frappe.get_doc("Batch", source_doc.lvm_batch)
	warehouse = batch_doc.get("lvm_location")
	batch_qty = batch_doc.get("batch_qty")
	batch_item = batch_doc.get("item")

	if not warehouse:
		frappe.throw(f"Batch {source_doc.lvm_batch} does not have a defined Location/Warehouse.")

	# 3. Add to Additional Costs
	repack_doc.append(
		"additional_costs",
		{
			"description": f"Capitalizing {source_doc.stock_entry_type} for batch {source_doc.lvm_batch}",
			"amount": source_doc.total_outgoing_value,  # Use total outgoing value
			"expense_account": expense_account,
		},
	)

	# 4. Append two rows: Raw Material (s_warehouse) and Finished Good (t_warehouse)
	# Row 1: Source (Raw Material)
	repack_doc.append(
		"items",
		{
			"item_code": batch_item,
			"batch_no": source_doc.lvm_batch,
			"s_warehouse": warehouse,
			"qty": batch_qty,  # Use the batch quantity for the source row
			"basic_rate": item_row.basic_rate,
			"use_serial_batch_fields": 1,
		},
	)

	# Row 2: Target (Finished Good)
	repack_doc.append(
		"items",
		{
			"item_code": batch_item,
			"batch_no": source_doc.lvm_batch,
			"t_warehouse": warehouse,
			"qty": batch_qty,  # Use the batch quantity for the target row
			"basic_rate": item_row.basic_rate,
			"is_finished_item": 1,
			"use_serial_batch_fields": 1,
		},
	)

	repack_doc.insert()
	repack_doc.submit()
