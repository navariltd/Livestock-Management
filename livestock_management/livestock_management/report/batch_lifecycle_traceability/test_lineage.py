from unittest import TestCase
from unittest.mock import patch

import frappe

from livestock_management.livestock_management.report.batch_lifecycle_traceability import lineage


class TestLineage(TestCase):
	def setUp(self):
		for mock in (
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(lineage, "_", side_effect=lambda x: x),
		):
			mock.start()
			self.addCleanup(mock.stop)
		self.items = dict(A="Bird", B="Bird", C="Bird", D="Bird")

	def classify(self, inputs, outputs, complete=True):
		allocations = {(b, "House", "out"): q for b, q in inputs.items()}
		allocations.update({(b, "House", "in"): q for b, q in outputs.items()})
		return lineage.classify_repack(allocations, complete, self.items)

	def test_split(self):
		result = self.classify(dict(A=100), dict(B=60, C=40))
		self.assertEqual(result["event_type"], "Split")
		self.assertEqual(result["parents"], ["A"])
		self.assertEqual(result["children"], ["B", "C"])

	def test_partial_split_retains_parent(self):
		result = self.classify(dict(A=100), dict(A=60, B=40))
		self.assertEqual(result["event_type"], "Split")
		self.assertEqual(result["children"], ["B"])

	def test_merge(self):
		result = self.classify(dict(A=60, B=40), dict(C=100))
		self.assertEqual(result["event_type"], "Merge")
		self.assertEqual(result["parents"], ["A", "B"])

	def test_replacement_and_cross_item_grading(self):
		self.assertEqual(self.classify(dict(A=100), dict(B=100))["event_type"], "Batch replacement")
		self.items["B"] = "Graded Bird"
		self.assertEqual(
			self.classify(dict(A=100), dict(B=100))["event_type"], "Reclassification / possible grading"
		)

	def test_unchanged_allocations_make_no_lineage(self):
		result = self.classify(dict(A=100), dict(A=100))
		self.assertEqual(result["event_type"], "Repack")
		self.assertEqual(result["parents"], [])

	def test_complex_unbalanced_fractional_and_incomplete_are_ambiguous(self):
		for inputs, outputs, complete in [
			(dict(A=60, B=40), dict(C=70, D=30), True),
			(dict(A=100), dict(B=99), True),
			(dict(A=100), dict(B=100), False),
			(dict(A=1.5), dict(B=1.5), True),
			(dict(A=100), {}, True),
			(dict(A=float("nan")), dict(B=100), True),
		]:
			with self.subTest(inputs=inputs, outputs=outputs):
				result = self.classify(inputs, outputs, complete)
				self.assertEqual(result["event_type"], "Ambiguous transformation")
				self.assertEqual(result["parents"], [])

	def test_traversal_both_directions_and_cycle(self):
		edges = {
			"split": self.classify(dict(A=100), dict(B=60, C=40)),
			"cycle": self.classify(dict(B=60), dict(A=60)),
		}
		self.assertEqual(lineage.reachable_batches("B", edges), {"A", "B", "C"})
		self.assertEqual(lineage.reachable_batches("B", edges, False), {"B"})

	def test_ambiguous_does_not_expand(self):
		self.assertEqual(lineage.reachable_batches("A", {"r": self.classify(dict(A=100), dict(B=90))}), {"A"})

	def test_expansion_limits_fail_instead_of_truncating(self):
		edges = {
			"ab": self.classify(dict(A=100), dict(B=100)),
			"bc": self.classify(dict(B=100), dict(C=100)),
			"cd": self.classify(dict(C=100), dict(D=100)),
		}
		for limits in (dict(MAX_BATCHES=3), dict(MAX_DEPTH=2)):
			with patch.multiple(lineage, **limits), self.assertRaises(frappe.ValidationError):
				lineage.reachable_batches("A", edges)

	def row(self, **kwargs):
		return frappe._dict(
			item_code="Bird", stock_uom="Nos", transfer_qty=100, s_warehouse="House", **kwargs
		)

	def test_bundle_replaces_legacy_batch_no(self):
		row = self.row(batch_no="LEGACY", serial_and_batch_bundle="BUNDLE")
		allocations, complete = lineage.repack_allocations(
			[row],
			{"BUNDLE": [frappe._dict(batch_no="A", qty=-60), frappe._dict(batch_no="B", qty=-40)]},
			{b: frappe._dict(item="Bird") for b in self.items},
			{"House"},
		)
		self.assertTrue(complete)
		self.assertEqual(allocations, {("A", "House", "out"): 60, ("B", "House", "out"): 40})

	def test_inaccessible_batch_warehouse_and_incomplete_bundle_block_inference(self):
		batches = {"A": frappe._dict(item="Bird")}
		for row, bundles, warehouses in [
			(self.row(batch_no="HIDDEN"), {}, {"House"}),
			(self.row(batch_no="A"), {}, {"Other"}),
			(self.row(serial_and_batch_bundle="MISSING"), {}, {"House"}),
			(self.row(serial_and_batch_bundle="B"), {"B": [frappe._dict(batch_no="A", qty=-50)]}, {"House"}),
		]:
			with self.subTest(row=row):
				self.assertFalse(lineage.repack_allocations([row], bundles, batches, warehouses)[1])

	def test_ledger_and_detail_allocations_must_match(self):
		self.assertFalse(lineage.same_allocations({("A", "House", "out"): 100}, {("A", "House", "out"): 90}))
		self.assertFalse(lineage.same_allocations({("A", "House", "out"): 100}, {("A", "Other", "out"): 100}))
