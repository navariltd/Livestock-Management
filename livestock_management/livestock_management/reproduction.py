import frappe
from frappe.utils import cint


def update_reproduction_counts(serial_no, *, services=0, diagnoses=0):
	"""Update counters under a row lock, in the calling document's transaction."""
	if not serial_no:
		return

	counts = frappe.db.get_value(
		"Serial No",
		serial_no,
		["custom_number_of_services", "custom_pregnancy_diagnosis"],
		as_dict=True,
		for_update=True,
	)
	if counts is None:
		frappe.throw(f"Serial No {serial_no} does not exist.")

	service_count = max(0, cint(counts.custom_number_of_services) + services)
	diagnosis_count = max(0, cint(counts.custom_pregnancy_diagnosis) + diagnoses)
	frappe.db.set_value(
		"Serial No",
		serial_no,
		{
			"custom_number_of_services": service_count,
			"custom_pregnancy_diagnosis": diagnosis_count,
			"custom_conception_rate_": diagnosis_count / service_count if service_count else 0,
		},
	)
	frappe.clear_document_cache("Serial No", serial_no)


def pregnancy_check_serial(doc):
	if (
		doc
		and doc.husbandry == "Pregnancy Check"
		and doc.serial_no
		and cint(doc.is_pregnant)
	):
		return doc.serial_no
	return None
