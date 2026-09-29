# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class WeightRecord(Document):
	def before_save(self):
		self.weight_gain = self.actual_weight - self.previous_weight
