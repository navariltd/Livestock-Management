from datetime import date, datetime
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.report.livestock_batch_performance_report import (
	livestock_batch_performance_report as report,
)


class TestBatchPerformance(TestCase):
	def setUp(self):
		self.translation = patch.object(report, "_", side_effect=lambda text: text)
		self.translation.start()
		self.addCleanup(self.translation.stop)
		self.filters = frappe._dict(from_date=date(2026, 10, 1), to_date=date(2026, 10, 10))
		self.batch = frappe._dict(name="FLOCK", manufacturing_date=date(2026, 9, 1))
		self.item = frappe._dict(name="BIRD", stock_uom="Nos")

	def movement(self, day, qty, voucher="RECEIPT", kind="Purchase Receipt"):
		return frappe._dict(
			date=date(2026, 10, day),
			timestamp=datetime(2026, 10, day, 12),
			qty=qty,
			voucher_no=voucher,
			voucher_type=kind,
		)

	def opening(self):
		return frappe._dict(
			date=date(2026, 9, 30),
			timestamp=datetime(2026, 9, 30),
			qty=100,
			voucher_no="OPEN",
			voucher_type="Purchase Receipt",
		)

	def row(self, moves, weights=None, operations=None, details=None, entries=None):
		return report.build_row(
			self.batch,
			self.item,
			moves,
			weights or [],
			operations or [],
			details or {},
			entries or {},
			self.filters,
		)

	def test_historical_balance_and_period_mortality(self):
		moves = [self.opening(), self.movement(3, -5, "DEATH", "Stock Entry")]
		row = self.row(moves, entries={"DEATH": frappe._dict(stock_entry_type="Mortality")})
		self.assertEqual(row["opening_qty"], 100)
		self.assertEqual(row["live_qty"], 95)
		self.assertEqual(row["mortality_qty"], 5)
		self.assertEqual(row["survival_percent"], 95)
		self.assertEqual(row["age_days"], 39)

	def test_sales_are_not_deaths_and_survival_is_unavailable(self):
		row = self.row([self.opening(), self.movement(4, -20, kind="Delivery Note")])
		self.assertEqual(row["live_qty"], 80)
		self.assertEqual(row["mortality_qty"], 0)
		self.assertIsNone(row["survival_percent"])

	def test_same_batch_repack_does_not_inflate_movements(self):
		row = self.row(
			[
				self.opening(),
				self.movement(4, -100, "REPACK", "Stock Entry"),
				self.movement(4, 100, "REPACK", "Stock Entry"),
			]
		)
		self.assertEqual(row["incoming_qty"], 0)
		self.assertEqual(row["outgoing_qty"], 0)
		self.assertEqual(row["live_qty"], 100)

	def test_feed_conversion_and_confirmed_interval_fcr(self):
		self.filters.weights_are_kg = 1
		weights = [
			frappe._dict(name="W1", posting_date=datetime(2026, 10, 1), actual_weight=1, sample_size=10),
			frappe._dict(name="W2", posting_date=datetime(2026, 10, 10), actual_weight=2, sample_size=10),
		]
		entry = frappe._dict(
			name="FEED",
			lvm_batch="FLOCK",
			stock_entry_type="Feeding",
			purpose="Material Issue",
			posting_date=date(2026, 10, 5),
			posting_time="12:00:00",
		)
		detail = frappe._dict(item_code="FEED", stock_qty=200, stock_uom="Kg", s_warehouse="STORE")
		row = self.row([self.opening()], weights, [entry], {"FEED": [detail]})
		self.assertEqual(row["feed_kg"], 200)
		self.assertEqual(row["fcr"], 2)
		self.filters.weights_are_kg = 0
		self.assertIsNone(self.row([self.opening()], weights, [entry], {"FEED": [detail]})["fcr"])

	def test_house_filter_does_not_guess_consumption(self):
		self.filters.warehouse = "HOUSE"
		row = self.row([self.opening()])
		self.assertIsNone(row["feed_kg"])
		self.assertIsNone(row["produce_qty"])

	def test_feed_conversion_requires_valid_factor(self):
		with patch.object(frappe, "db", Mock(get_value=Mock(return_value=50))):
			self.assertEqual(report.to_kg("FEED", "g", 100), 2)
		with patch.object(frappe, "db", Mock(get_value=Mock(return_value=None))):
			self.assertIsNone(report.to_kg("FEED", "Bag", 10))
