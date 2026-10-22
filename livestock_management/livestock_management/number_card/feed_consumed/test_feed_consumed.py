from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.number_card.feed_consumed import feed_consumed as card


class TestFeedConsumed(TestCase):
	def setUp(self):
		for mock in (
			patch.object(frappe, "in_test", True),
			patch.object(card, "_", side_effect=lambda text: text),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(card, "nowdate", return_value="2026-10-22"),
			patch.object(frappe.defaults, "get_user_default", return_value="Farm"),
		):
			mock.start()
			self.addCleanup(mock.stop)

	def row(self, quantity=10, uom="Kg", item="Feed"):
		return frappe._dict(item_code=item, transfer_qty=quantity, stock_uom=uom, s_warehouse="Store")

	def test_stock_kg_are_summed_not_documents_or_money(self):
		self.assertEqual(card.sum_feed_kg([self.row(10), self.row(20)]), (30, None))

	def test_stock_uom_conversion_is_applied_once(self):
		with patch.object(card, "to_kg", return_value=50) as convert:
			self.assertEqual(card.sum_feed_kg([self.row(2, "Bag"), self.row(3, "Bag")]), (250, None))
			convert.assert_called_once_with("Feed", "Bag", 1)

	def test_mixed_convertible_units_are_combined(self):
		with patch.object(card, "to_kg", side_effect=[1, 0.001]):
			self.assertEqual(card.sum_feed_kg([self.row(2), self.row(500, "Gram", "Other")]), (2.5, None))

	def test_missing_conversion_does_not_return_partial_total(self):
		with patch.object(card, "to_kg", side_effect=[1, None]):
			self.assertIsNone(card.sum_feed_kg([self.row(2), self.row(3, "Bag", "Other")])[0])

	def test_nonfinite_or_negative_quantities_are_unavailable(self):
		for quantity in [-1, 0, float("nan"), float("inf")]:
			with self.subTest(quantity=quantity):
				self.assertIsNone(card.sum_feed_kg([self.row(quantity)])[0])

	def test_invalid_warehouse_direction_is_unavailable(self):
		row = self.row()
		row.t_warehouse = "Destination"
		self.assertIsNone(card.sum_feed_kg([row])[0])
		row = self.row()
		row.s_warehouse = None
		self.assertIsNone(card.sum_feed_kg([row])[0])

	def test_no_rows_is_zero(self):
		self.assertEqual(card.sum_feed_kg([]), (0, None))

	def test_invalid_filters_or_dates_do_not_query_stock(self):
		with patch.object(frappe, "get_list") as query:
			for filters in [["bad"], {"from_date": "2026-10-23"}, {"to_date": "2026-10-23"}]:
				with self.subTest(filters=filters), self.assertRaises(frappe.ValidationError):
					card.get(filters=filters)
			query.assert_not_called()

	def test_permission_failure_stops_stock_read(self):
		with (
			patch.object(frappe, "get_doc", side_effect=frappe.PermissionError),
			patch.object(frappe, "get_list") as query,
		):
			with self.assertRaises(frappe.PermissionError):
				card.get()
			query.assert_not_called()

	def run_endpoint(self, house=None, row=None):
		context = patch.multiple(
			frappe,
			get_doc=Mock(return_value=Mock(company="Farm", is_group=0)),
			has_permission=Mock(return_value=True),
			get_meta=Mock(return_value=Mock(has_field=Mock(return_value=True))),
		)
		with (
			context,
			patch.object(
				frappe,
				"get_list",
				side_effect=[
					["Bird"],
					["FLOCK"],
					[frappe._dict(name="FEED-1", lvm_livestock_house="House")],
					["Store"],
					["Feed"],
				],
			) as query,
			patch.object(frappe, "get_all", return_value=[row or self.row(12.5)]) as children,
		):
			result = card.get(filters={"warehouse": house} if house else [])
			return result, query.call_args_list, children.call_args

	def test_endpoint_filters_posted_feed_for_flagged_batches(self):
		result, calls, children = self.run_endpoint()
		self.assertEqual(result["value"], 12.5)
		self.assertEqual(result["fieldtype"], "Float")
		self.assertEqual(result["uom"], "Kg")
		self.assertEqual(result["from_date"], "2026-10-01")
		filters = calls[2].kwargs["filters"]
		self.assertEqual(filters["docstatus"], 1)
		self.assertEqual(filters["stock_entry_type"], "Feeding")
		self.assertEqual(filters["purpose"], "Material Issue")
		self.assertEqual(filters["lvm_batch"], ["in", ["FLOCK"]])
		self.assertIn("transfer_qty", children.kwargs["fields"])
		self.assertEqual(calls[1].kwargs["filters"]["lvm_is_livestock_item"], 1)

	def test_house_filter_uses_livestock_house_not_feed_store(self):
		result, _, _ = self.run_endpoint(house="House")
		self.assertEqual(result["value"], 12.5)

	def test_inaccessible_feed_warehouse_is_not_included(self):
		row = self.row()
		row.s_warehouse = "Private Store"
		result, _, _ = self.run_endpoint(row=row)
		self.assertIsNone(result["value"])

	def test_missing_house_does_not_show_an_incomplete_house_total(self):
		with (
			patch.object(frappe, "get_doc", return_value=Mock(company="Farm", is_group=0)),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(
				frappe,
				"get_list",
				side_effect=[["Bird"], ["FLOCK"], [frappe._dict(name="OLD", lvm_livestock_house=None)]],
			),
			patch.object(frappe, "get_all") as children,
		):
			result = card.get(filters={"warehouse": "House"})
			self.assertIsNone(result["value"])
			self.assertIn("house", result["reason"])
			children.assert_not_called()

	def test_no_matching_livestock_is_zero_not_document_count(self):
		with (
			patch.object(frappe, "get_doc", return_value=Mock()),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(frappe, "get_list", return_value=[]),
			patch.object(frappe, "get_all") as children,
		):
			result = card.get()
			self.assertEqual(result["value"], 0)
			children.assert_not_called()
