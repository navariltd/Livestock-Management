from datetime import datetime
from unittest import TestCase
from unittest.mock import patch

import frappe

from livestock_management.livestock_management.number_card.internal_fcr import internal_fcr as card


class TestInternalFCR(TestCase):
	def setUp(self):
		self.moves = {
			"BIRD": [
				frappe._dict(
					qty=100,
					date="2026-09-30",
					timestamp=datetime(2026, 9, 30),
					warehouse="House",
					voucher_type="Purchase Receipt",
					voucher_no="OPEN",
				)
			]
		}
		self.weights = [
			frappe._dict(
				name="W1",
				batch="BIRD",
				posting_date="2026-10-01 08:00:00",
				actual_weight=1,
				sample_size=10,
				lvm_weight_uom="Kg",
				lvm_livestock_house="House",
			),
			frappe._dict(
				name="W2",
				batch="BIRD",
				posting_date="2026-10-10 08:00:00",
				actual_weight=2,
				sample_size=10,
				lvm_weight_uom="Kg",
				lvm_livestock_house="House",
			),
		]
		self.entries = [
			frappe._dict(
				name="FEED",
				lvm_batch="BIRD",
				lvm_livestock_house="House",
				posting_date="2026-10-05",
				posting_time="12:00:00",
			)
		]
		self.rows = [
			frappe._dict(
				parent="FEED", item_code="Feed", stock_uom="Kg", transfer_qty=200, s_warehouse="Store"
			)
		]

	def calculate(self):
		return card.calculate_fcr(self.moves, self.weights, self.entries, self.rows, "2026-10-01")

	def test_feed_divided_by_population_weight_gain(self):
		value, reason, intervals = self.calculate()
		self.assertEqual(value, 2)
		self.assertIsNone(reason)
		self.assertEqual(intervals[0]["gain_kg"], 100)

	def test_aggregate_uses_total_feed_over_total_gain(self):
		self.moves["OTHER"] = [frappe._dict(self.moves["BIRD"][0], qty=10)]
		self.weights.extend([frappe._dict(w, name=w.name + "-OTHER", batch="OTHER") for w in self.weights[:]])
		self.entries.append(frappe._dict(self.entries[0], name="OTHERFEED", lvm_batch="OTHER"))
		self.rows.append(frappe._dict(self.rows[0], parent="OTHERFEED", transfer_qty=50))
		self.assertEqual(self.calculate()[0], 2.27)

	def test_same_day_feed_before_measurement_is_excluded(self):
		self.entries.append(
			frappe._dict(self.entries[0], name="EARLY", posting_date="2026-10-01", posting_time="07:00:00")
		)
		self.rows.append(frappe._dict(self.rows[0], parent="EARLY", transfer_qty=999))
		self.assertEqual(self.calculate()[0], 2)

	def test_feed_after_last_weight_is_excluded(self):
		self.entries.append(
			frappe._dict(self.entries[0], name="LATE", posting_date="2026-10-10", posting_time="09:00:00")
		)
		self.rows.append(frappe._dict(self.rows[0], parent="LATE", transfer_qty=999))
		self.assertEqual(self.calculate()[0], 2)

	def test_missing_or_unconfirmed_weights_are_unavailable(self):
		self.weights.pop()
		self.assertIsNone(self.calculate()[0])

	def test_unknown_weight_units_are_not_assumed_to_be_kg(self):
		self.weights[-1].lvm_weight_uom = None
		self.assertIsNone(self.calculate()[0])

	def test_zero_gain_is_unavailable(self):
		self.weights[-1].actual_weight = 1
		self.assertIsNone(self.calculate()[0])

	def test_invalid_sample_is_unavailable(self):
		self.weights[-1].sample_size = 101
		self.assertIsNone(self.calculate()[0])

	def test_stock_movement_between_weights_is_unavailable(self):
		self.moves["BIRD"].append(
			frappe._dict(
				qty=-1,
				date="2026-10-02",
				timestamp=datetime(2026, 10, 2),
				warehouse="House",
				voucher_type="Stock Entry",
				voucher_no="DEATH",
			)
		)
		self.assertIsNone(self.calculate()[0])

	def test_valuation_repack_does_not_count_as_weight_gain_or_feed(self):
		for qty in (-100, 100):
			self.moves["BIRD"].append(
				frappe._dict(
					qty=qty,
					date="2026-10-02",
					timestamp=datetime(2026, 10, 2),
					warehouse="House",
					voucher_type="Stock Entry",
					voucher_no="REPACK",
				)
			)
		self.assertEqual(self.calculate()[0], 2)

	def test_no_feed_records_is_unavailable_not_zero_fcr(self):
		self.entries = []
		self.assertIsNone(self.calculate()[0])

	def test_one_incomplete_batch_does_not_silently_drop_from_summary(self):
		self.moves["OTHER"] = [frappe._dict(self.moves["BIRD"][0])]
		self.assertIsNone(self.calculate()[0])

	def test_missing_conversion_is_unavailable(self):
		with patch.object(card, "sum_feed_kg", return_value=(None, "Missing conversion")):
			self.assertIsNone(self.calculate()[0])

	def test_permission_failure_stops_queries(self):
		with (
			patch.object(frappe, "in_test", True),
			patch.object(card, "validate_scope", side_effect=frappe.PermissionError),
			patch.object(card, "nowdate", return_value="2026-10-22"),
			patch.object(frappe, "get_list") as query,
		):
			with self.assertRaises(frappe.PermissionError):
				card.get(filters={"company": "Hidden"})
			query.assert_not_called()

	def test_response_has_ratio_format_not_currency_or_percent(self):
		result = card.response(2, dict(company="Farm", from_date="2026-10-01", to_date="2026-10-10"), None)
		self.assertEqual(result["fieldtype"], "Float")
		self.assertEqual(result["precision"], 2)
		self.assertEqual(result["uom"], "kg feed / kg live-weight gain")

	def test_missing_data_formats_as_na(self):
		with patch.object(card, "_", side_effect=lambda x: x):
			result = card.response(
				None, dict(company="Farm", from_date="2026-10-01", to_date="2026-10-10"), "Missing weights"
			)
			self.assertIsNone(result["value"])

	def test_endpoint_reads_scoped_weights_and_only_submitted_feed(self):
		with (
			patch.object(frappe, "in_test", True),
			patch.object(card, "validate_scope"),
			patch.object(card, "nowdate", return_value="2026-10-22"),
			patch.object(frappe.defaults, "get_user_default", return_value="Farm"),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(card, "get_batch_movements", return_value=self.moves),
			patch.object(
				frappe,
				"get_list",
				side_effect=[["Bird"], ["BIRD"], ["House", "Store"], self.weights, self.entries, ["Feed"]],
			) as query,
			patch.object(frappe, "get_all", return_value=self.rows),
		):
			result = card.get(filters=[])
			self.assertEqual(result["value"], 2)
			feed_filter = query.call_args_list[4].kwargs["filters"]
			self.assertEqual(feed_filter["docstatus"], 1)
			self.assertEqual(feed_filter["stock_entry_type"], "Feeding")
			self.assertEqual(feed_filter["purpose"], "Material Issue")
			self.assertEqual(query.call_args_list[1].kwargs["filters"]["lvm_is_livestock_item"], 1)

	def test_equal_measurement_timestamps_are_unavailable(self):
		self.weights[-1].posting_date = self.weights[0].posting_date
		self.assertIsNone(self.calculate()[0])
