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
