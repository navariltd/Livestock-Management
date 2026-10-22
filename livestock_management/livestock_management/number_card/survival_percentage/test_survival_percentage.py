from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.number_card.survival_percentage import (
	survival_percentage as card,
)


class TestSurvivalPercentage(TestCase):
	def moves(self, *rows):
		return {
			"FLOCK": [
				frappe._dict(date=getdate, qty=qty, voucher_type=kind, voucher_no=name)
				for getdate, qty, kind, name in rows
			]
		}

	def opening(self, qty=100):
		return (date(2026, 9, 30), qty, "Purchase Receipt", "OPEN")

	def period(self, qty, kind="Stock Entry", name="DEATH"):
		return (date(2026, 10, 2), qty, kind, name)

	def calculate(self, moves, entries=None):
		return card.calculate_survival(moves, entries or {}, date(2026, 10, 1))

	def death(self):
		return frappe._dict(stock_entry_type="Mortality", purpose="Material Issue")

	def test_zero_deaths_is_full_survival(self):
		self.assertEqual(self.calculate(self.moves(self.opening()))[0], 100)

	def test_mortality_uses_animal_quantity(self):
		self.assertEqual(
			self.calculate(self.moves(self.opening(), self.period(-5)), {"DEATH": self.death()}),
			(95, None, 100, 5),
		)

	def test_sales_do_not_count_as_mortality(self):
		self.assertEqual(
			self.calculate(self.moves(self.opening(), self.period(-20, "Delivery Note", "SALE")))[0], 100
		)

	def test_receipts_enter_the_denominator(self):
		self.assertEqual(
			self.calculate(
				self.moves(self.period(100, "Purchase Receipt", "BUY"), self.period(-5)),
				{"DEATH": self.death()},
			)[0],
			95,
		)

	def test_transfer_and_repack_have_no_company_population_effect(self):
		entries = {
			"TRANSFER": frappe._dict(purpose="Material Transfer", stock_entry_type="Material Transfer"),
			"REPACK": frappe._dict(purpose="Repack", stock_entry_type="Capitalisation"),
		}
		moves = self.moves(
			self.opening(),
			self.period(-100, name="TRANSFER"),
			self.period(100, name="TRANSFER"),
			self.period(-100, name="REPACK"),
			self.period(100, name="REPACK"),
		)
		self.assertEqual(self.calculate(moves, entries)[0], 100)

	def test_combined_rate_is_population_weighted(self):
		moves = self.moves(self.opening(100), self.period(-10))
		moves["OTHER"] = [
			frappe._dict(date=date(2026, 9, 30), qty=900, voucher_type="Purchase Receipt", voucher_no="OTHER")
		]
		self.assertEqual(self.calculate(moves, {"DEATH": self.death()})[0], 99)

	def test_empty_or_zero_population_is_unavailable(self):
		self.assertIsNone(self.calculate({})[0])
		self.assertIsNone(self.calculate(self.moves(self.opening(0)))[0])

	def test_negative_or_excessive_mortality_is_unavailable(self):
		self.assertIsNone(
			self.calculate(self.moves(self.opening(), self.period(-101)), {"DEATH": self.death()})[0]
		)

	def test_unreadable_stock_voucher_is_unavailable(self):
		self.assertIsNone(self.calculate(self.moves(self.opening(), self.period(-5)))[0])

	def test_stock_corrections_are_unavailable(self):
		self.assertIsNone(
			self.calculate(self.moves(self.opening(), self.period(-5, "Stock Reconciliation", "FIX")))[0]
		)

	def test_partial_batch_transformation_is_unavailable(self):
		self.assertIsNone(
			self.calculate(
				self.moves(self.opening(), self.period(-50, name="SPLIT")),
				{"SPLIT": frappe._dict(purpose="Repack", stock_entry_type="Repack")},
			)[0]
		)

	def test_unclassified_animal_issue_is_unavailable(self):
		self.assertIsNone(
			self.calculate(
				self.moves(self.opening(), self.period(-5)),
				{"DEATH": frappe._dict(purpose="Material Issue", stock_entry_type="Material Issue")},
			)[0]
		)

	def test_previous_period_deaths_are_already_in_opening_balance(self):
		moves = self.moves(self.opening(), (date(2026, 9, 30), -10, "Stock Entry", "OLD"))
		self.assertEqual(self.calculate(moves)[0], 100)

	def test_endpoint_defaults_and_uses_only_flagged_batches(self):
		with (
			patch.object(frappe, "in_test", True),
			patch.object(card, "_", side_effect=lambda x: x),
			patch.object(frappe.defaults, "get_user_default", return_value="Farm"),
			patch.object(card, "nowdate", return_value="2026-10-22"),
			patch.object(card, "validate_scope"),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[["Bird"], ["FLOCK"]]) as query,
			patch.object(card, "get_batch_movements", return_value=self.moves(self.opening())),
		):
			result = card.get(filters=[])
			self.assertEqual(result["value"], 100)
			self.assertEqual(result["fieldtype"], "Percent")
			self.assertEqual(result["from_date"], "2026-10-01")
			self.assertEqual(query.call_args.kwargs["filters"]["lvm_is_livestock_item"], 1)

	def test_permission_failure_does_not_read_stock(self):
		with (
			patch.object(frappe, "in_test", True),
			patch.object(card, "nowdate", return_value="2026-10-22"),
			patch.object(card, "validate_scope", side_effect=frappe.PermissionError),
			patch.object(card, "get_batch_movements") as stock,
		):
			with self.assertRaises(frappe.PermissionError):
				card.get(filters={"company": "Hidden"})
			stock.assert_not_called()

	def test_one_negative_batch_cannot_be_hidden_by_another(self):
		moves = self.moves(self.opening(100))
		moves["INVALID"] = [
			frappe._dict(date=date(2026, 9, 30), qty=-5, voucher_type="Delivery Note", voucher_no="BAD")
		]
		self.assertIsNone(self.calculate(moves)[0])

	def test_all_animals_dying_is_zero_percent_not_unavailable(self):
		self.assertEqual(
			self.calculate(self.moves(self.opening(), self.period(-100)), {"DEATH": self.death()})[0], 0
		)

	def test_explicit_culling_is_not_mortality(self):
		self.assertEqual(
			self.calculate(
				self.moves(self.opening(), self.period(-10, name="CULL")),
				{"CULL": frappe._dict(purpose="Material Issue", stock_entry_type="Culling")},
			)[0],
			100,
		)
