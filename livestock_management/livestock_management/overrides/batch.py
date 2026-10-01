import frappe
from frappe import _
from frappe.utils import add_days, getdate


def before_batch_save(doc, method):
	"""
	Calculates Capitalisation End Date based on Start Date + Capitalisation Days.
	"""
	if not doc.lvm_capitalisation_start_date and doc.manufacturing_date:
		doc.lvm_capitalisation_start_date = doc.manufacturing_date

	if doc.lvm_capitalisation_start_date and doc.lvm_capitalization_days:
		try:
			start_date = getdate(doc.lvm_capitalisation_start_date)
			days = int(doc.lvm_capitalization_days)

			doc.lvm_capitalisation_end_date = add_days(start_date, days)
			doc.lvm_age_in_weeks = days // 7
		except (ValueError, TypeError):
			frappe.msgprint(_("Invalid date or capitalization days format."))
