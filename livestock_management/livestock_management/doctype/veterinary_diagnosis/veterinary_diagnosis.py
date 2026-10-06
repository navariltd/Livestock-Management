# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class VeterinaryDiagnosis(Document):
	def before_submit(self):
		if self.status == "Pending":
			frappe.throw(
				_(
					"Cannot submit a diagnosis with status 'Pending'. Please update the status before submitting."
				)
			)

	def validate(self):
		"""Auto-set the end date to the current date if status is 'Completed' and end date is not provided."""
		if self.status == "Completed" and not self.end_date:
			self.end_date = frappe.utils.nowdate()
