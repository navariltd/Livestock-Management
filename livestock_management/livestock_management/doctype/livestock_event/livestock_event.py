# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from livestock_management.livestock_management.reproduction import (
	pregnancy_check_serial,
	update_reproduction_counts,
)


class LivestockEvent(Document):
	def on_update(self):
		previous_serial = pregnancy_check_serial(self.get_doc_before_save())
		current_serial = pregnancy_check_serial(self)
		if previous_serial == current_serial:
			return

		# Stable lock order when an event moves between animals.
		for serial_no in sorted({previous_serial, current_serial} - {None}):
			update_reproduction_counts(serial_no, diagnoses=1 if serial_no == current_serial else -1)

	def on_trash(self):
		serial_no = pregnancy_check_serial(self)
		if serial_no:
			update_reproduction_counts(serial_no, diagnoses=-1)
