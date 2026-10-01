# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from livestock_management.livestock_management.reproduction import update_reproduction_counts


class BreedingRecord(Document):
	def on_submit(self):
		update_reproduction_counts(self.dam, services=1)

	def on_cancel(self):
		update_reproduction_counts(self.dam, services=-1)
