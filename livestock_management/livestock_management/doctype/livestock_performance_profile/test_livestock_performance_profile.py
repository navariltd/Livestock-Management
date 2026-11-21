from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.doctype.livestock_performance_profile import (
	livestock_performance_profile as module,
)
from livestock_management.livestock_management.overrides.batch import validate_performance_profile
from livestock_management.livestock_management.testing import pin_count_uoms


class TargetRow(frappe._dict):
	def set(self, key, value):
		self[key] = value


class TestPerformanceProfile(TestCase):
	def setUp(self):
		pin_count_uoms(self)
		for mock in (
			patch.object(module, "_", side_effect=lambda x: x),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
		):
			mock.start()
			self.addCleanup(mock.stop)

	def validate(self, targets, laying=0, items=None):
		doc = frappe._dict(
			targets=[TargetRow(t) for t in targets],
			all_female_laying_flock=laying,
			egg_items=[frappe._dict(item=i) for i in (items or [])],
		)
		module.LivestockPerformanceProfile.validate(doc)
		return doc

	def test_blank_and_zero_are_distinct_and_age_zero_is_valid(self):
		doc = self.validate([dict(age_days=0, weight_kg="0", feed_g=" ", fcr="1.25")])
		self.assertEqual(doc.targets[0].weight_kg, "0.0")
		self.assertIsNone(doc.targets[0].feed_g)
		self.assertEqual(doc.targets[0].fcr, "1.25")

	def test_rejects_duplicate_negative_and_fractional_ages(self):
		for targets in ([dict(age_days=1), dict(age_days=1)], [dict(age_days=-1)], [dict(age_days=1.5)], []):
			with self.subTest(targets=targets), self.assertRaises(frappe.ValidationError):
				self.validate(targets)

	def test_weeks_fill_days_and_days_fill_weeks(self):
		doc = self.validate([dict(age_weeks=2.5), dict(age_days=0, age_weeks=1), dict(age_days=10)])
		self.assertEqual(
			[(r.age_days, r.age_weeks) for r in doc.targets],
			[(18, 2.57), (7, 1.0), (10, 1.43)],
		)

	def test_two_decimal_weeks_round_trip_to_the_same_day(self):
		for days in range(0, 1000):
			with self.subTest(days=days):
				self.assertEqual(module.weeks_to_days(module.days_to_weeks(days)), days)

	def test_rejects_conflicting_weeks_and_days(self):
		with self.assertRaises(frappe.ValidationError):
			self.validate([dict(age_days=10, age_weeks=2)])
		self.validate([dict(age_days=14, age_weeks=2)])
		with self.assertRaises(frappe.ValidationError):
			self.validate([dict(age_weeks=1), dict(age_days=7)])
		with self.assertRaises(frappe.ValidationError):
			self.validate([dict(age_weeks=-1)])

	def test_cumulative_mortality_converts_to_constant_daily_rates(self):
		rates = module.daily_mortality_from_cumulative(range(10), [(0, 1), (7, 3)])
		self.assertEqual(rates[0], 1.0)
		expected = round(100 * (1 - (97 / 99) ** (1 / 7)), 4)
		self.assertEqual({rates[age] for age in range(1, 8)}, {expected})
		self.assertNotIn(8, rates)  # after the last point: left unchanged

	def test_cumulative_and_daily_mortality_round_trip(self):
		points = [(0, 0.5), (7, 1.2), (21, 2.5), (35, 4)]
		rates = module.daily_mortality_from_cumulative(range(36), points)
		back = dict(module.cumulative_mortality_from_daily(list(rates.items())))
		for age, cumulative in points:
			with self.subTest(age=age):
				self.assertAlmostEqual(back[age], cumulative, places=2)
		self.assertEqual(module.cumulative_mortality_from_daily([(0, 1), (1, None), (2, 1)]), [(0, 1.0)])

	def test_full_mortality_and_rejected_cumulative_points(self):
		self.assertEqual(
			module.daily_mortality_from_cumulative([3, 4], [(3, 100), (4, 100)]), {3: 100, 4: 100}
		)
		for points in ([(1, 2), (2, 1)], [(1, 101)], [(1, 1), (1, 2)], [(-1, 1)], [(1.5, 1)], [(1, None)]):
			with self.subTest(points=points), self.assertRaises(frappe.ValidationError):
				module.daily_mortality_from_cumulative([1], points)

	def test_form_helpers_accept_json_arguments(self):
		with patch.object(frappe, "parse_json", side_effect=frappe.json.loads):
			rates = module.convert_cumulative_mortality(
				"[0, 1]", '[{"age_days": 1, "cumulative_percent": 2}]'
			)
			self.assertEqual(set(rates), {"0", "1"})
			self.assertEqual(
				module.cumulative_mortality('[{"age_days": 0, "mortality_percent": "1"}]'),
				[{"age_days": 0, "cumulative_percent": 1.0}],
			)

	def test_invalid_numbers_and_percentages(self):
		for value in ("no", "NaN", "inf", "-1"):
			with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
				self.validate([dict(age_days=0, feed_g=value)])
		with self.assertRaises(frappe.ValidationError):
			self.validate([dict(age_days=0, egg_yield_percent="100.1")])
		self.validate([dict(age_days=0, egg_yield_percent="100")])
		with self.assertRaises(frappe.ValidationError):
			self.validate([dict(age_days=0, mortality_percent="100.1")])
		doc = self.validate([dict(age_days=0, mortality_percent="0.05")])
		self.assertEqual(doc.targets[0].mortality_percent, "0.05")

	def test_laying_requires_items_and_rejects_duplicates_or_non_count_items(self):
		with self.assertRaises(frappe.ValidationError):
			self.validate([dict(age_days=0)], laying=1)
		item = Mock(is_stock_item=1, stock_uom="Nos")
		with patch.object(frappe, "get_doc", return_value=item):
			self.validate([dict(age_days=0)], laying=1, items=["Egg"])
			item.check_permission.assert_called_with("read")
			with self.assertRaises(frappe.ValidationError):
				self.validate([dict(age_days=0)], laying=1, items=["Egg", "Egg"])
			item.stock_uom = "Kg"
			with self.assertRaises(frappe.ValidationError):
				self.validate([dict(age_days=0)], laying=1, items=["Egg"])

	def test_batch_assignment_requires_submitted_readable_profile(self):
		with patch.object(frappe, "get_doc", return_value=Mock(docstatus=1)) as query:
			validate_performance_profile(frappe._dict(lvm_performance_profile="PROFILE"))
			query.return_value.check_permission.assert_called_with("read")
			query.return_value.docstatus = 0
			with (
				patch("livestock_management.livestock_management.overrides.batch._", side_effect=lambda x: x),
				self.assertRaises(frappe.ValidationError),
			):
				validate_performance_profile(frappe._dict(lvm_performance_profile="PROFILE"))
