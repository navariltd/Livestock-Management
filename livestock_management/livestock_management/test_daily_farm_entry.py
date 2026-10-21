# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

import frappe

from livestock_management.livestock_management import daily_farm_entry as entry


class TestDailyFarmEntry(TestCase):
	def setUp(self):
		for mock in (
			patch.object(entry, "_", side_effect=lambda text: text),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(frappe, "db", Mock()),
		):
			mock.start()
			self.addCleanup(mock.stop)
		self.context = dict(
			company="Farm",
			item="Bird",
			batch="Flock",
			house="House",
			employee="Employee",
			posting_datetime="2026-10-21 08:00:00",
		)
		self.payload = dict(
			activity="mortality",
			operation_id=str(uuid4()),
			context=self.context,
			values=dict(quantity=2, reason="Disease"),
		)

	def test_reject_invalid_quantities(self):
		for value in (0, -1, float("inf"), float("nan"), "invalid"):
			with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
				entry.positive(value)

	def test_payload_hash_ignores_key_order(self):
		self.assertEqual(entry.request_hash({"b": 2, "a": 1}), entry.request_hash({"a": 1, "b": 2}))
		self.assertNotEqual(entry.request_hash({"a": 1}), entry.request_hash({"a": 2}))

	def test_reject_field_injection(self):
		with self.assertRaises(frappe.ValidationError):
			entry.validate_keys({"quantity": 1, "docstatus": 1}, {"quantity"})

	def test_invalid_uuid_never_inserts(self):
		self.payload["operation_id"] = "bad"
		with patch.object(frappe, "new_doc") as new_doc:
			with self.assertRaises(frappe.ValidationError):
				entry.save_activity(self.payload)
			new_doc.assert_not_called()

	def test_unsupported_activity(self):
		self.payload["activity"] = "Journal Entry"
		with self.assertRaises(frappe.ValidationError):
			entry.save_activity(self.payload)

	def test_duplicate_request_returns_existing_without_creating(self):
		with (
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(entry, "existing_operation", return_value={"name": "STE-1"}),
			patch.object(entry, "validate_context") as validate,
		):
			self.assertEqual(entry.save_activity(self.payload), {"name": "STE-1"})
			validate.assert_not_called()

	def test_existing_request_requires_read_and_matching_hash(self):
		frappe.db.get_value.return_value = "STE-1"
		doc = Mock(lvm_farm_entry_hash="old")
		with patch.object(entry, "checked_doc", return_value=doc) as checked:
			with self.assertRaises(frappe.ValidationError):
				entry.existing_operation("Stock Entry", "id", "different")
			checked.assert_called_once_with("Stock Entry", "STE-1")

	def test_create_permission_denied_before_context_or_insert(self):
		with (
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(entry, "existing_operation", return_value=None),
			patch.object(frappe, "has_permission", side_effect=frappe.PermissionError),
			patch.object(entry, "validate_context") as validate,
		):
			with self.assertRaises(frappe.PermissionError):
				entry.save_activity(self.payload)
			validate.assert_not_called()

	def test_mortality_uses_livestock_identity_and_never_submits(self):
		doc = Mock(doctype="Stock Entry")
		with (
			patch.object(frappe, "new_doc", return_value=doc),
			patch.object(entry, "checked_doc", return_value=frappe._dict(purpose="Material Issue")),
			patch.object(entry, "population", return_value=100),
		):
			entry.make_document(
				"mortality",
				self.context,
				self.payload["values"],
				frappe._dict(name="Bird", stock_uom="Nos"),
				frappe._dict(name="Flock"),
				datetime(2026, 10, 21, 8),
			)
			row = doc.append.call_args.args[1]
			self.assertEqual(row["batch_no"], "Flock")
			self.assertEqual(row["s_warehouse"], "House")
			doc.submit.assert_not_called()

	def test_mortality_rejects_over_population(self):
		with (
			patch.object(frappe, "new_doc", return_value=Mock(doctype="Stock Entry")),
			patch.object(entry, "checked_doc", return_value=frappe._dict(purpose="Material Issue")),
			patch.object(entry, "population", return_value=1),
		):
			with self.assertRaises(frappe.ValidationError):
				entry.make_document(
					"mortality",
					self.context,
					self.payload["values"],
					frappe._dict(name="Bird", stock_uom="Nos"),
					frappe._dict(name="Flock"),
					datetime(2026, 10, 21, 8),
				)

	def test_stock_rows_do_not_use_livestock_batch_for_feed(self):
		doc = Mock()
		item = frappe._dict(name="Feed", stock_uom="Kg", is_stock_item=1, has_batch_no=0)
		with patch.object(entry, "checked_doc", return_value=item), patch.object(entry, "validate_warehouse"):
			entry.add_stock_rows(
				doc, "feeding", [dict(item="Feed", quantity=10, warehouse="Feed Store")], self.context
			)
		row = doc.append.call_args.args[1]
		self.assertIsNone(row["batch_no"])
		self.assertEqual(row["s_warehouse"], "Feed Store")

	def test_reject_stock_row_accounts_or_status(self):
		with self.assertRaises(frappe.ValidationError):
			entry.add_stock_rows(
				Mock(), "feeding", [{"item": "Feed", "expense_account": "Injected"}], self.context
			)

	def test_missing_inventory_batch_is_rejected(self):
		item = frappe._dict(name="Feed", is_stock_item=1, has_batch_no=1)
		with patch.object(entry, "checked_doc", return_value=item), patch.object(entry, "validate_warehouse"):
			with self.assertRaises(frappe.ValidationError):
				entry.add_stock_rows(
					Mock(), "feeding", [dict(item="Feed", quantity=1, warehouse="Store")], self.context
				)

	def test_unique_constraint_collision_recovers_after_rollback(self):
		doc = Mock()
		doc.insert.side_effect = frappe.UniqueValidationError
		with (
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(entry, "existing_operation", side_effect=[None, {"name": "STE-1"}]),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(entry, "validate_context", return_value=(Mock(), Mock(), datetime(2026, 10, 21))),
			patch.object(entry, "make_document", return_value=doc),
		):
			self.assertEqual(entry.save_activity(self.payload), {"name": "STE-1"})
			frappe.db.rollback.assert_called_once_with(save_point="farm_activity_insert")
			doc.submit.assert_not_called()
