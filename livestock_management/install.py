import frappe


def after_install():
	create_custom_stock_entry_types()


def create_custom_stock_entry_types():
	stock_entry_types = [
		{
			"stock_entry_type": "Treatment",
			"purpose": "Material Issue",
		},
		{
			"stock_entry_type": "Feeding",
			"purpose": "Material Issue",
		},
		{
			"stock_entry_type": "Capitalisation",
			"purpose": "Repack",
		},
		{
			"stock_entry_type": "Mortality",
			"purpose": "Material Issue",
		},
	]

	for entry_type in stock_entry_types:
		if frappe.db.exists("Stock Entry Type", entry_type["stock_entry_type"]):
			continue

		doc = frappe.new_doc("Stock Entry Type")
		doc.name = entry_type["stock_entry_type"]
		doc.title = entry_type["stock_entry_type"]
		doc.stock_entry_type = entry_type["stock_entry_type"]
		doc.purpose = entry_type["purpose"]
		doc.insert(ignore_permissions=True)
