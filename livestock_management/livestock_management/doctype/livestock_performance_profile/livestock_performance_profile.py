from math import floor, isfinite

import frappe
from frappe import _
from frappe.model.document import Document

from livestock_management.livestock_management.stock_units import is_count_uom

TARGET_FIELDS = ("weight_kg", "feed_g", "fcr", "egg_yield_percent")


def target_number(value):
	"""Data fields preserve blank versus explicit zero through Frappe persistence/import."""
	if value is None or (isinstance(value, str) and not value.strip()):
		return None
	try:
		result = float(value)
	except (TypeError, ValueError):
		raise frappe.ValidationError(_("Targets must be numbers.")) from None
	if not isfinite(result) or result < 0:
		raise frappe.ValidationError(_("Targets must be finite, non-negative numbers."))
	return result


def weeks_to_days(weeks):
	"""Nearest whole day, rounding halves up to match the form's Math.round."""
	return floor(weeks * 7 + 0.5)


def days_to_weeks(days):
	return round(days / 7, 2)


def target_age_days(row):
	"""Resolve a row's age in days from Age (Days), or from Age (Weeks) when days is blank/zero."""
	days = target_number(row.age_days)
	weeks = target_number(row.get("age_weeks"))
	if weeks and not days:
		return weeks_to_days(weeks)
	if days is not None and weeks and weeks_to_days(weeks) != days:
		frappe.throw(
			_("Age (Weeks) {0} does not match Age (Days) {1}. Clear one of them.").format(weeks, days)
		)
	return days


class LivestockPerformanceProfile(Document):
	def validate(self):
		seen = set()
		for row in self.targets:
			age = target_age_days(row)
			if age is None or not float(age).is_integer() or age in seen:
				frappe.throw(_("Target ages must be unique, non-negative whole days."))
			seen.add(age)
			row.set("age_days", int(age))
			row.set("age_weeks", days_to_weeks(age))
			for field in TARGET_FIELDS:
				value = target_number(row.get(field))
				if field == "egg_yield_percent" and value is not None and value > 100:
					frappe.throw(_("Hen-day egg yield cannot exceed 100%."))
				row.set(field, None if value is None else str(value))
		if not self.targets:
			frappe.throw(_("Enter at least one age target row."))
		if self.all_female_laying_flock and not self.egg_items:
			frappe.throw(_("Select all eligible egg Items for a laying profile."))
		seen_items = set()
		for row in self.egg_items:
			if row.item in seen_items:
				frappe.throw(_("Egg Items must be unique."))
			seen_items.add(row.item)
			item = frappe.get_doc("Item", row.item)
			item.check_permission("read")
			if not item.is_stock_item or not is_count_uom(item.stock_uom):
				frappe.throw(_("Egg Items must be stock Items counted in a Livestock Count UOM."))
