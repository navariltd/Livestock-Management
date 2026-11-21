from itertools import pairwise
from math import floor, isfinite

import frappe
from frappe import _
from frappe.model.document import Document

from livestock_management.livestock_management.stock_units import is_count_uom

TARGET_FIELDS = ("weight_kg", "feed_g", "fcr", "egg_yield_percent", "mortality_percent")
PERCENT_FIELDS = {
	"egg_yield_percent": "Hen-day egg yield cannot exceed 100%.",
	"mortality_percent": "Daily mortality cannot exceed 100%.",
}
MORTALITY_PRECISION = 4


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
				if field in PERCENT_FIELDS and value is not None and value > 100:
					frappe.throw(_(PERCENT_FIELDS[field]))
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


def daily_mortality_from_cumulative(ages, points):
	"""Convert cumulative mortality points into a daily rate for each target age they cover.

	Each point is (age_days, cumulative %): the share of placed animals dead by the end of
	that day, counted from day 0. Between two points the daily rate is held constant, so it
	is the geometric rate that turns the earlier survival into the later one. Ages after the
	last point are left out of the result.
	"""
	intervals, prev_age, prev_cumulative = [], -1, 0.0
	for age, cumulative in sorted(_mortality_points(points)):
		if prev_cumulative >= 100:
			rate = 100.0
		else:
			survival = (100 - cumulative) / (100 - prev_cumulative)
			rate = 100 * (1 - survival ** (1 / (age - prev_age)))
		intervals.append((prev_age, age, rate))
		prev_age, prev_cumulative = age, cumulative
	result = {}
	for age in ages:
		rate = next((rate for low, high, rate in intervals if low < age <= high), None)
		if rate is not None:
			result[age] = round(rate, MORTALITY_PRECISION)
	return result


def cumulative_mortality_from_daily(rows):
	"""Inverse of daily_mortality_from_cumulative for (age_days, daily %) rows.

	Each row's rate covers the days since the previous row. Stops at the first row without a
	rate, because every later cumulative figure would be unknown.
	"""
	result, survival, prev_age = [], 1.0, -1
	for age, daily in sorted(rows, key=lambda row: row[0]):
		if daily is None:
			break
		survival *= (1 - daily / 100) ** (age - prev_age)
		prev_age = age
		result.append((age, round(100 * (1 - survival), MORTALITY_PRECISION)))
	return result


def _mortality_points(points):
	seen, result = set(), []
	for age, cumulative in points:
		age, cumulative = target_number(age), target_number(cumulative)
		if age is None or not age.is_integer() or age in seen:
			frappe.throw(_("Cumulative mortality ages must be unique, non-negative whole days."))
		if cumulative is None or cumulative > 100:
			frappe.throw(_("Cumulative mortality must be between 0 and 100%."))
		seen.add(age)
		result.append((int(age), cumulative))
	result.sort()
	for (_age, earlier), (age, later) in pairwise(result):
		if later < earlier:
			frappe.throw(_("Cumulative mortality cannot fall between days ({0}).").format(age))
	return result


@frappe.whitelist()
def convert_cumulative_mortality(ages: str, points: str) -> dict:
	"""Form helper: {age_days: daily %} for the given target ages."""
	result = daily_mortality_from_cumulative(
		[int(age) for age in frappe.parse_json(ages)],
		[(p.get("age_days"), p.get("cumulative_percent")) for p in frappe.parse_json(points)],
	)
	return {str(age): rate for age, rate in result.items()}


@frappe.whitelist()
def cumulative_mortality(rows: str) -> list:
	"""Form helper: cumulative % at each target age, from its daily rates."""
	return [
		{"age_days": age, "cumulative_percent": cumulative}
		for age, cumulative in cumulative_mortality_from_daily(
			[(int(r["age_days"]), target_number(r.get("mortality_percent"))) for r in frappe.parse_json(rows)]
		)
	]
