import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

from livestock_management.livestock_management.stock_units import COUNT_UOM_FIELD, DEFAULT_COUNT_UOMS


def execute():
	"""Install the UOM flag before fixtures sync and keep Nos/Unit counting livestock as before."""
	create_custom_field(
		"UOM",
		{
			"fieldname": COUNT_UOM_FIELD,
			"fieldtype": "Check",
			"label": "Livestock Count UOM",
			"insert_after": "must_be_whole_number",
		},
	)
	for uom in DEFAULT_COUNT_UOMS:
		if frappe.db.exists("UOM", uom):
			frappe.db.set_value("UOM", uom, COUNT_UOM_FIELD, 1, update_modified=False)
	frappe.flags.pop("lvm_count_uoms", None)
