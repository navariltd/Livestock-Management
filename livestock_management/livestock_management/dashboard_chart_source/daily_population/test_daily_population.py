from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management import batch_stock
from livestock_management.livestock_management.dashboard_chart_source.daily_population import (
	daily_population as source,
)


class TestDailyPopulation(TestCase):
	def setUp(self):
		for mock in (
			patch.object(source, "_", side_effect=lambda text: text),
			patch.object(batch_stock, "_", side_effect=lambda text: text),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(source, "nowdate", return_value="2026-10-22"),
			patch.object(frappe.defaults, "get_user_default", return_value=None),
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
		):
			mock.start()
			self.addCleanup(mock.stop)

	def moves(self, *entries):
		return {"FLOCK": [frappe._dict(date=day, qty=qty) for day, qty in entries]}

	def test_opening_movements_and_days_without_activity(self):
		labels, values = source.daily_balances(
			self.moves(("2026-09-30", 100), ("2026-10-02", -2), ("2026-10-04", -10)),
			"2026-10-01",
			"2026-10-04",
		)
		self.assertEqual(labels, ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"])
		self.assertEqual(values, [100, 98, 98, 88])

	def test_transfers_and_valuation_repacks_net_to_zero(self):
		_, values = source.daily_balances(
			self.moves(
				("2026-09-30", 100),
				("2026-10-01", -100),
				("2026-10-01", 100),
				("2026-10-02", -20),
				("2026-10-02", 20),
			),
			"2026-10-01",
			"2026-10-02",
		)
		self.assertEqual(values, [100, 100])

	def test_house_departure_reduces_balance(self):
		_, values = source.daily_balances(
			self.moves(("2026-09-30", 100), ("2026-10-02", -20)), "2026-10-01", "2026-10-02"
		)
		self.assertEqual(values, [100, 80])

	def test_end_date_is_inclusive_and_later_entries_are_ignored(self):
		_, values = source.daily_balances(
			self.moves(("2026-10-01", 50), ("2026-10-02", 500)), "2026-10-01", "2026-10-01"
		)
		self.assertEqual(values, [50])

	def test_empty_history_returns_daily_zeros(self):
		self.assertEqual(source.daily_balances({}, "2026-10-01", "2026-10-02")[1], [0, 0])

	def test_invalid_ranges_and_missing_filters_do_not_query_stock(self):
		with patch.object(source, "get_batch_movements") as stock:
			for args in [
				dict(filters={}),
				dict(
					filters={"company": "Farm", "item_code": "Bird"},
					from_date="2026-10-02",
					to_date="2026-10-01",
				),
				dict(filters={"company": "Farm", "item_code": "Bird"}, to_date="2026-10-23"),
				dict(filters={"company": "Farm", "item_code": "Bird"}, from_date="2020-01-01"),
				dict(filters={"company": "Farm", "item_code": "Bird"}, timespan="Select Date Range"),
				dict(filters={"company": "Farm", "item_code": "Bird"}, time_interval="Monthly"),
			]:
				with self.subTest(args=args), self.assertRaises(frappe.ValidationError):
					source.get(**args)
			stock.assert_not_called()

	def test_one_history_read_for_entire_chart(self):
		with (
			patch.object(source, "validate_scope"),
			patch.object(frappe, "get_list", side_effect=[["Bird"], ["FLOCK"]]),
			patch.object(
				source, "get_batch_movements", return_value=self.moves(("2026-09-30", 100))
			) as stock,
		):
			result = source.get(
				filters='{"company":"Farm","item_code":"Bird"}', from_date="2026-10-01", to_date="2026-10-03"
			)
			self.assertEqual(result["datasets"][0]["values"], [100, 100, 100])
			stock.assert_called_once()

	def test_scope_permission_failure_stops_stock_query(self):
		with (
			patch.object(frappe, "get_doc", side_effect=frappe.PermissionError),
			patch.object(source, "get_batch_movements") as stock,
		):
			with self.assertRaises(frappe.PermissionError):
				source.get(filters={"company": "Hidden", "item_code": "Bird"})
			stock.assert_not_called()

	def test_rejects_weight_based_inventory(self):
		doc = Mock(is_stock_item=1, has_batch_no=1, stock_uom="Kg")
		with patch.object(frappe, "get_doc", return_value=doc):
			with self.assertRaises(frappe.ValidationError):
				source.validate_scope(frappe._dict(company="Farm", item_code="Bird"))

	def test_default_company_and_all_flagged_batches(self):
		with (
			patch.object(frappe.defaults, "get_user_default", return_value="Farm"),
			patch.object(source, "validate_scope"),
			patch.object(frappe, "get_list", side_effect=[["Bird", "Cow"], ["FLOCK", "HERD"]]) as query,
			patch.object(
				source,
				"get_batch_movements",
				return_value={
					"FLOCK": [frappe._dict(date="2026-10-01", qty=100)],
					"HERD": [frappe._dict(date="2026-10-01", qty=20)],
				},
			) as stock,
		):
			result = source.get(filters=[], from_date="2026-10-01", to_date="2026-10-02")
			self.assertEqual(result["datasets"][0]["values"], [120, 120])
			self.assertEqual(stock.call_args.args[0].company, "Farm")
			self.assertEqual(
				query.call_args.kwargs["filters"],
				{"lvm_is_livestock_item": 1, "item": ["in", ["Bird", "Cow"]]},
			)

	def test_no_eligible_items_returns_zero_without_ledger_query(self):
		with (
			patch.object(source, "validate_scope"),
			patch.object(frappe, "get_list", return_value=[]),
			patch.object(batch_stock.frappe, "has_permission") as permission,
		):
			result = source.get(filters={"company": "Farm"}, from_date="2026-10-01", to_date="2026-10-02")
			self.assertEqual(result["datasets"][0]["values"], [0, 0])
			permission.assert_not_called()

	def test_rejects_explicit_non_livestock_batch(self):
		company = Mock()
		batch = frappe._dict(item="Feed", lvm_is_livestock_item=0)
		batch.check_permission = Mock()
		with patch.object(frappe, "get_doc", side_effect=[company, batch]):
			with self.assertRaises(frappe.ValidationError):
				source.validate_scope(frappe._dict(company="Farm", batch="FEED"))

	def test_aggregate_ledger_query_scopes_permitted_items(self):
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[["House"], []]) as query,
		):
			batch_stock.get_batch_movements(
				frappe._dict(company="Farm", item_codes=["Bird", "Cow"], to_date=date(2026, 10, 2)),
				["FLOCK", "HERD"],
			)
			self.assertEqual(query.call_args.kwargs["filters"]["item_code"], ["in", ["Bird", "Cow"]])

	def test_bundle_quantities_replace_legacy_fields(self):
		ledger = [
			frappe._dict(
				name="SLE1",
				warehouse="House",
				posting_date="2026-10-01",
				posting_time="12:00:00",
				actual_qty=100,
				batch_no="FLOCK",
				serial_and_batch_bundle="BUNDLE",
				voucher_type="Purchase Receipt",
				voucher_no="PR1",
			),
			frappe._dict(
				name="SLE2",
				warehouse="House",
				posting_date="2026-10-02",
				posting_time="12:00:00",
				actual_qty=-2,
				batch_no="FLOCK",
				voucher_type="Stock Entry",
				voucher_no="SE1",
			),
		]
		children = [
			frappe._dict(parent="BUNDLE", batch_no="FLOCK", qty=60),
			frappe._dict(parent="BUNDLE", batch_no="OTHER", qty=40),
		]
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", side_effect=[["House"], ledger]) as get_list,
			patch.object(frappe, "get_all", return_value=children),
		):
			moves = batch_stock.get_batch_movements(
				frappe._dict(company="Farm", item_code="Bird", to_date=date(2026, 10, 2)), ["FLOCK"]
			)
			self.assertEqual([m.qty for m in moves["FLOCK"]], [60, -2])
			query = get_list.call_args.kwargs["filters"]
			self.assertEqual(query["is_cancelled"], 0)
			self.assertEqual(query["docstatus"], ["<", 2])
			self.assertEqual(query["warehouse"], ["in", ["House"]])

	def test_unreadable_warehouses_do_not_query_ledger(self):
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", return_value=[]) as get_list,
		):
			self.assertEqual(batch_stock.get_batch_movements(frappe._dict(company="Farm"), ["FLOCK"]), {})
			self.assertEqual(get_list.call_count, 1)
