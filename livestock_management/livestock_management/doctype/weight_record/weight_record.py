# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


@frappe.whitelist()
def get_previous_weight_record(
	weight_record: str, batch: str, posting_date: str, weight_uom: str, current_record: str | None = None
) -> dict:
	"""Return a readable earlier weight record after validating its selection context."""
	if not all((weight_record, batch, posting_date, weight_uom)):
		frappe.throw(_("Batch, posting date, UOM, and previous Weight Record are required."))

	frappe.has_permission("Weight Record", "read", throw=True)
	frappe.get_doc("Batch", batch).check_permission("read")
	previous = frappe.get_doc("Weight Record", weight_record)
	previous.check_permission("read")

	if current_record and previous.name == current_record:
		frappe.throw(_("A Weight Record cannot be used as its own previous measurement."))
	if previous.docstatus == 2:
		frappe.throw(_("Cancelled Weight Records cannot be selected."))
	if previous.batch != batch:
		frappe.throw(_("Select a Weight Record for the same batch."))
	if previous.lvm_weight_uom != weight_uom:
		frappe.throw(_("The selected Weight Record uses a different weight UOM."))
	if not previous.posting_date or get_datetime(previous.posting_date) >= get_datetime(posting_date):
		frappe.throw(_("Select a Weight Record recorded before this entry."))

	return {
		"name": previous.name,
		"posting_date": previous.posting_date,
		"actual_weight": previous.actual_weight,
		"age": previous.age,
		"weight_uom": previous.lvm_weight_uom,
	}


class WeightRecord(Document):
	def before_save(self):
		self.weight_gain = self.actual_weight - self.previous_weight
