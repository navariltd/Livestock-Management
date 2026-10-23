from datetime import datetime
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.utils import getdate

from livestock_management.livestock_management import batch_stock
from livestock_management.livestock_management.report.batch_lifecycle_traceability import sources


class TestLifecycleSources(TestCase):
	def context(self):
		context = sources.LifecycleSources.__new__(sources.LifecycleSources)
		context.filters = frappe._dict(
			company="Farm", batch="A", to_date=getdate("2026-10-03"), warehouse="House"
		)
		context.notices = set()
		context.docs = {}
		context.warehouses = {"House"}
		context.batches = {"A": frappe._dict(item="Bird"), "B": frappe._dict(item="Bird")}
		context.movements = {}
		context.transformations = {}
		return context

	def move(self, voucher="ENTRY", qty=100):
		return frappe._dict(voucher_type="Stock Entry", voucher_no=voucher, qty=qty, warehouse="House")

	def test_parent_documents_are_permission_aware_submitted_and_company_scoped(self):
		context = self.context()
		context.movements = {"A": [frappe._dict(voucher_type="Sales Invoice", voucher_no="SI")]}
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(frappe, "get_list", return_value=[]) as query,
		):
			context.load_stock_documents()
			calls = {call.args[0]: call.kwargs for call in query.call_args_list}
			self.assertEqual(calls["Sales Invoice"]["filters"]["update_stock"], 1)
			self.assertEqual(calls["Sales Invoice"]["filters"]["name"], ["in", ["SI"]])
			for call in calls.values():
				self.assertEqual(call["filters"]["company"], "Farm")
				self.assertEqual(call["filters"]["docstatus"], 1)
				self.assertNotIn("warehouse", call["filters"])

	def test_unreadable_sources_do_not_query_children_or_leak_names(self):
		context = self.context()
		context.movements = {"A": [self.move("HIDDEN")]}
		with (
			patch.object(frappe, "has_permission", return_value=False),
			patch.object(frappe, "get_list") as query,
			patch.object(frappe, "get_all") as children,
		):
			context.load_stock_documents()
			context.remove_hidden_vouchers()
			self.assertEqual(context.load_transformations(), {})
			self.assertEqual(context.movements["A"], [])
			query.assert_not_called()
			children.assert_not_called()
			self.assertNotIn("HIDDEN", " ".join(context.notices))

	def test_complete_stock_children_and_ledger_required_to_infer(self):
		context = self.context()
		context.docs = {
			"Stock Entry": {"R": frappe._dict(name="R", purpose="Repack", stock_entry_type="Repack")}
		}
		context.movements = {"A": [self.move("R", -100)], "B": [self.move("R", 100)]}
		children = [
			frappe._dict(
				parent="R",
				item_code="Bird",
				stock_uom="Nos",
				transfer_qty=100,
				batch_no=b,
				s_warehouse="House" if b == "A" else None,
				t_warehouse="House" if b == "B" else None,
			)
			for b in ("A", "B")
		]
		with patch.object(frappe, "get_all", return_value=children) as query:
			result = context.load_transformations()
			self.assertEqual(result["R"]["children"], ["B"])
			self.assertEqual(query.call_args.kwargs["filters"], {"parent": ["in", ["R"]]})
			context.movements["B"] = []
			self.assertEqual(context.load_transformations()["R"]["event_type"], "Ambiguous transformation")

	def test_capitalisation_never_creates_descendant_even_if_legacy_data_malformed(self):
		context = self.context()
		context.docs = {
			"Stock Entry": {"R": frappe._dict(name="R", purpose="Repack", stock_entry_type="Capitalisation")}
		}
		context.movements = {"A": [self.move("R", -100)], "B": [self.move("R", 100)]}
		with patch.object(frappe, "get_all", return_value=[]):
			result = context.load_transformations()["R"]
			self.assertEqual(result["event_type"], "Capitalisation")
			self.assertEqual(result["parents"], [])

	def test_optional_activity_permissions_and_historical_scope(self):
		context = self.context()
		with (
			patch.object(frappe, "has_permission", return_value=False),
			patch.object(frappe, "get_list") as query,
		):
			self.assertEqual(context.activities({"A"}), {})
			query.assert_not_called()
			self.assertTrue(any("Veterinary Diagnosis" in text for text in context.notices))

		def query(doctype, **kwargs):
			return (
				[
					frappe._dict(name="A", batch="A", posting_date="2026-10-02", lvm_livestock_house="House"),
					frappe._dict(
						name="HIDDEN", batch="A", posting_date="2026-10-02", lvm_livestock_house="Hidden"
					),
				]
				if doctype == "Weight Record"
				else []
			)

		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(frappe, "get_list", side_effect=query) as queries,
		):
			result = context.activities({"A"})
			self.assertEqual([r.name for r in result["Weight Record"]], ["A"])
			calls = {call.args[0]: call.kwargs for call in queries.call_args_list}
			self.assertEqual(calls["Weight Record"]["filters"]["lvm_company"], "Farm")
			self.assertEqual(calls["Livestock Event"]["filters"]["status"], "Completed")
			self.assertEqual(calls["Veterinary Diagnosis"]["filters"]["docstatus"], 1)
			self.assertNotIn("HIDDEN", " ".join(context.notices))

	def test_diagnosis_house_can_come_from_its_explicit_readable_medical_entry(self):
		context = self.context()
		context.docs = {"Stock Entry": {"MED": frappe._dict(lvm_batch="A", lvm_livestock_house="House")}}

		def query(doctype, **kwargs):
			return (
				[frappe._dict(name="VET", batch="A", diagnosis_date="2026-10-02", medical_stock_entry="MED")]
				if doctype == "Veterinary Diagnosis"
				else []
			)

		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(frappe, "get_list", side_effect=query),
		):
			self.assertEqual(context.activities({"A"})["Veterinary Diagnosis"][0].lifecycle_house, "House")

	def test_empty_warehouse_scope_and_unclassified_historical_batches(self):
		# No livestock-checkbox filter is applied; count-based stock Item eligibility is authoritative.
		def query(doctype, **kwargs):
			if doctype == "Item":
				return [frappe._dict(name="Bird", stock_uom="Nos")]
			if doctype == "Batch":
				return [frappe._dict(name="A", item="Bird")]
			return []

		with (
			patch.object(frappe, "get_list", side_effect=query) as calls,
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_meta", return_value=Mock(has_field=Mock(return_value=True))),
			patch.object(sources, "get_batch_movements", return_value={}) as ledger,
		):
			context = sources.LifecycleSources(self.context().filters)
			self.assertIn("A", context.batches)
			batch_call = next(c for c in calls.call_args_list if c.args[0] == "Batch")
			self.assertNotIn("lvm_is_livestock_item", batch_call.kwargs["filters"])
			self.assertNotIn("warehouse", ledger.call_args.args[0])

	def test_shared_reader_uses_bundles_once_and_legacy_when_no_bundle(self):
		rows = [
			frappe._dict(
				name="S1",
				posting_date="2026-10-01",
				posting_time="12:00:00",
				actual_qty=-100,
				batch_no="WRONG",
				serial_and_batch_bundle="BUNDLE",
				voucher_type="Stock Entry",
				voucher_no="R",
				warehouse="House",
			),
			frappe._dict(
				name="S2",
				posting_date="2026-10-01",
				posting_time="12:00:00",
				actual_qty=100,
				batch_no="B",
				voucher_type="Stock Entry",
				voucher_no="R",
				warehouse="House",
			),
		]
		with patch.object(
			frappe, "get_all", return_value=[frappe._dict(parent="BUNDLE", batch_no="A", qty=-100)]
		):
			movements = batch_stock.expand_batch_ledger(rows, ["A", "B"])
			self.assertEqual([m.qty for m in movements["A"]], [-100])
			self.assertEqual([m.qty for m in movements["B"]], [100])
			self.assertNotIn("WRONG", movements)
