# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime

from livestock_management.livestock_management.reproduction import (
	pregnancy_check_serial,
	update_reproduction_counts,
)


class LivestockEvent(Document):
	def validate(self):
		if not self.starts_on:
			frappe.throw(_("Starts On is required."))
		if not self.ends_on:
			self.ends_on = self.starts_on
		if get_datetime(self.ends_on) < get_datetime(self.starts_on):
			frappe.throw(_("Ends On cannot be before Starts On."))

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


@frappe.whitelist()
def get_events(start: str, end: str, filters: str | list | None = None) -> list[frappe._dict]:
	"""Return overlapping dated events using the current user's read permissions."""
	filters = frappe.parse_json(filters) if filters else []
	if not isinstance(filters, list):
		frappe.throw(_("Calendar filters must be a list."))
	filters = [
		*filters,
		["Livestock Event", "starts_on", "is", "set"],
		["Livestock Event", "starts_on", "<=", get_datetime(end)],
		["Livestock Event", "ends_on", ">=", get_datetime(start)],
	]
	return frappe.get_list(
		"Livestock Event",
		fields=["name", "husbandry", "starts_on", "ends_on"],
		filters=filters,
		order_by="starts_on asc",
		limit_page_length=0,
	)
