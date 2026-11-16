import frappe

OBSOLETE_FIELDS = ("custom_column_break_oakmv", "custom_column_break_rl6in")


def execute():
	"""Drop obsolete Stock Entry column breaks; customisation sync never deletes Custom Fields."""
	for fieldname in OBSOLETE_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": "Stock Entry", "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
