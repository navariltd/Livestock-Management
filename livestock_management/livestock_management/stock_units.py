"""Stock quantity conversions shared by reports and cards."""

import frappe
from frappe.utils import flt


def to_kg(item_code, stock_uom, qty):
	if stock_uom == "Kg":
		return flt(qty)
	# An Item conversion factor specifies stock units per alternate UOM.
	conversion = frappe.db.get_value(
		"UOM Conversion Detail", {"parent": item_code, "uom": "Kg"}, "conversion_factor"
	)
	return flt(qty) / flt(conversion) if flt(conversion) > 0 else None


COUNT_UOM_FIELD = "lvm_is_count_uom"
DEFAULT_COUNT_UOMS = ("Nos", "Unit")


def get_count_uoms():
	"""UOMs where one stock unit is one animal or egg; population, mortality and yield maths rely on it."""
	if "lvm_count_uoms" not in frappe.flags:
		# Plain SQL: a site-wide setting that must not be row-permission filtered.
		if frappe.db.has_column("UOM", COUNT_UOM_FIELD):
			uoms = frappe.db.sql_list(f"SELECT name FROM `tabUOM` WHERE `{COUNT_UOM_FIELD}` = 1")
		else:
			# Before migration installs the flag, keep the historical behaviour.
			uoms = list(DEFAULT_COUNT_UOMS)
		frappe.flags.lvm_count_uoms = tuple(uoms)
	return list(frappe.flags.lvm_count_uoms)


def is_count_uom(uom):
	return uom in get_count_uoms()


def count_uom_filter():
	"""Item `stock_uom` filter value; never empty, since an empty `in` list matches nothing useful."""
	return ["in", get_count_uoms() or [""]]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def count_item_query(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: dict | list | str | None = None,
):
	"""Link-field search for Items stocked in a Livestock Count UOM."""
	from frappe.desk.search import search_widget

	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	if isinstance(filters, dict):
		filters = dict(filters, stock_uom=count_uom_filter())
	else:
		filters = [*filters, ["Item", "stock_uom", *count_uom_filter()]]
	return search_widget(
		"Item", txt, searchfield=searchfield, start=start, page_length=page_len, filters=filters
	)


def flag_default_count_uom(doc, method=None):
	"""UOM before_insert: Nos/Unit created after install (e.g. by the setup wizard) count livestock."""
	if doc.uom_name in DEFAULT_COUNT_UOMS and doc.meta.has_field(COUNT_UOM_FIELD):
		doc.set(COUNT_UOM_FIELD, 1)
