import frappe
from frappe import _
from frappe.utils import cint


def validate(doc, method=None):
	if not cint(doc.get("lvm_to_capitalize")):
		return

	if not cint(doc.get("has_batch_no")):
		frappe.throw(_("Enable Has Batch No for Items marked To Capitalize."))

	if cint(doc.get("lvm_capitalization_days")) <= 0:
		frappe.throw(_("Capitalization Days must be greater than 0 for Items marked To Capitalize."))
