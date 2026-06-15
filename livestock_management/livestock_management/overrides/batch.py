import frappe
from frappe.utils import add_days, getdate

def before_batch_save(doc, method):
    """
    Calculates Capitalisation End Date based on Start Date + Capitalisation Days.
    """
    if doc.lvm_capitalisation_start_date and doc.lvm_capitalization_days:
        try:
            start_date = getdate(doc.lvm_capitalisation_start_date)
            days = int(doc.lvm_capitalization_days)

            doc.lvm_capitalisation_end_date = add_days(start_date, days)
        except (ValueError, TypeError):
            frappe.msgprint("Invalid date or capitalization days format.")
