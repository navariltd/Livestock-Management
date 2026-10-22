from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.doctype.livestock_performance_profile import (
	livestock_performance_profile as module,
)
from livestock_management.livestock_management.overrides.batch import validate_performance_profile


class TargetRow(frappe._dict):
	def set(self, key, value):
		self[key] = value


class TestPerformanceProfile(TestCase):
	def setUp(self):
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

	def test_invalid_numbers_and_percentages(self):
		for value in ("no", "NaN", "inf", "-1"):
			with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
				self.validate([dict(age_days=0, feed_g=value)])
		with self.assertRaises(frappe.ValidationError):
			self.validate([dict(age_days=0, egg_yield_percent="100.1")])
		self.validate([dict(age_days=0, egg_yield_percent="100")])

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
