# In a patch file or custom app's hooks.py after_migrate
import frappe


def execute():
	make_fields_optional()


def make_fields_optional():
	for field in ["reference_type", "reference_name"]:
		frappe.make_property_setter(
			{
				"doctype": "Quality Inspection",
				"fieldname": field,
				"property": "reqd",
				"value": 0,
				"property_type": "Check",
			}
		)
	frappe.db.commit()
