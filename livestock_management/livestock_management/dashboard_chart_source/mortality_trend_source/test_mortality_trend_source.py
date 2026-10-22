from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.dashboard_chart_source.mortality_trend_source import (
	mortality_trend_source as source,
)


class TestMortalityTrend(TestCase):
	def setUp(self):
		for mock in (
			patch.object(frappe, "in_test", True),
			patch.object(source, "_", side_effect=lambda text: text),
			patch.object(source, "nowdate", return_value="2026-10-22"),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(frappe.defaults, "get_user_default", return_value="Farm"),
		):
			mock.start()
			self.addCleanup(mock.stop)

	def movement(self, day="2026-10-01", qty=-10, voucher="DEATH", kind="Stock Entry"):
		return frappe._dict(date=day, qty=qty, voucher_no=voucher, voucher_type=kind)

	def test_counts_animals_and_fills_quiet_days(self):
		labels, values = source.daily_deaths(
			{"A": [self.movement(), self.movement(qty=-2)], "B": [self.movement(qty=-3)]},
			{"DEATH"},
			"2026-10-01",
			"2026-10-03",
		)
		self.assertEqual(labels, ["2026-10-01", "2026-10-02", "2026-10-03"])
		self.assertEqual(values, [15, 0, 0])

	def test_excludes_other_vouchers_inward_and_out_of_range(self):
		moves = [
			self.movement(voucher="SALE"),
			self.movement(qty=20),
			self.movement(kind="Stock Reconciliation"),
			self.movement(day="2026-09-30"),
			self.movement(day="2026-10-03"),
			self.movement(day="2026-10-02", qty=-4),
		]
		_, values = source.daily_deaths({"A": moves}, {"DEATH"}, "2026-10-01", "2026-10-02")
		self.assertEqual(values, [0, 4])

	def test_empty_history_returns_zeros(self):
		self.assertEqual(source.daily_deaths({}, set(), "2026-10-01", "2026-10-02")[1], [0, 0])

	def test_source_scopes_permissions_batches_dates_and_house(self):
		with (
			patch.object(source, "validate_scope") as scope,
			patch.object(frappe, "has_permission") as permission,
			patch.object(frappe, "get_list", side_effect=[["Bird"], ["A"], ["DEATH"]]) as query,
			patch.object(source, "get_batch_movements", return_value={"A": [self.movement()]}) as stock,
		):
			result = source.get(filters={"warehouse": "House"}, from_date="2026-10-01", to_date="2026-10-02")
			self.assertEqual(result["datasets"][0]["values"], [10, 0])
			self.assertEqual(scope.call_args.args[0]["company"], "Farm")
			permission.assert_called_once_with("Stock Entry", "read", throw=True)
			self.assertEqual(stock.call_args.args[0]["warehouse"], "House")
			self.assertEqual(stock.call_args.args[1], ["A"])
			self.assertEqual(query.call_args_list[1].kwargs["filters"]["lvm_is_livestock_item"], 1)
			entry_filters = query.call_args_list[2].kwargs["filters"]
			self.assertEqual(entry_filters["docstatus"], 1)
			self.assertEqual(entry_filters["stock_entry_type"], "Mortality")
			self.assertEqual(entry_filters["purpose"], "Material Issue")
			self.assertEqual(str(entry_filters["posting_date"][1][0]), "2026-10-01")

	def test_no_permitted_entries_skips_stock(self):
		with (
			patch.object(source, "validate_scope"),
			patch.object(frappe, "has_permission"),
			patch.object(frappe, "get_list", side_effect=[["Bird"], ["A"], []]),
			patch.object(source, "get_batch_movements") as stock,
		):
			result = source.get(filters=[], from_date="2026-10-01", to_date="2026-10-02")
			self.assertEqual(result["datasets"][0]["values"], [0, 0])
			stock.assert_not_called()

	def test_scope_failure_stops_stock(self):
		with (
			patch.object(source, "validate_scope", side_effect=frappe.PermissionError),
			patch.object(source, "get_batch_movements") as stock,
		):
			with self.assertRaises(frappe.PermissionError):
				source.get(filters={"company": "Hidden"})
			stock.assert_not_called()

	def test_invalid_filters_interval_and_dates(self):
		for kwargs in (
			{"filters": ["invalid"]},
			{"time_interval": "Weekly"},
			{"from_date": "2026-10-02", "to_date": "2026-10-01"},
			{"to_date": "2026-10-23"},
			{"timespan": "Select Date Range"},
		):
			with self.subTest(kwargs=kwargs), self.assertRaises(frappe.ValidationError):
				source.get(**kwargs)

	def test_chart_settings_supply_saved_filters(self):
		chart = Mock()
		chart.get.side_effect = {
			"filters_json": '{"company":"Farm","batch":"A"}',
			"time_interval": "Daily",
			"timespan": "Last Week",
		}.get
		with (
			patch.object(frappe, "get_doc", return_value=chart),
			patch.object(source, "validate_scope"),
			patch.object(frappe, "has_permission"),
			patch.object(frappe, "get_list", return_value=[]) as query,
		):
			result = source.get(chart_name="Mortality Trend")
			chart.check_permission.assert_called_once_with("read")
			self.assertTrue(result["labels"])
			self.assertEqual(query.call_args.kwargs["filters"]["stock_uom"], ["in", ["Nos", "Unit"]])
