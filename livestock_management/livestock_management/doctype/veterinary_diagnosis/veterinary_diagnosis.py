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

		# Set the start and end dates on the treatment_plans table rows based on self.start_date and self.end_date
		for treatment_plan in self.treatment_plans:
			if not treatment_plan.start_date and self.start_date:
				treatment_plan.start_date = self.start_date
			if not treatment_plan.end_date and self.end_date:
				treatment_plan.end_date = self.end_date
