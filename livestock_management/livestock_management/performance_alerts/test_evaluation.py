from datetime import datetime
from unittest import TestCase

import frappe

from livestock_management.livestock_management.performance_alerts.evaluation import (
	detect,
	detect_treatment,
	latest_valid_weight,
	occupancy,
)


class TestDetection(TestCase):
	def setUp(self):
		self.batch = frappe._dict(name="B", lvm_hatch_date="2026-10-01")
		self.rule = frappe._dict(
			alert_type="Mortality",
			mortality_percent=2,
			minimum_deaths=2,
			weight_shortfall_percent=10,
			max_gap_days=2,
		)
		self.profile = frappe._dict(targets=[frappe._dict(age_days=20, weight_kg="2")])
		self.moves = [self.move(100, "2026-10-01 07:00:00")]
		self.weight = frappe._dict(
			name="W",
			posting_date="2026-10-21 08:00:00",
			actual_weight=1.5,
			sample_size=10,
			lvm_weight_uom="Kg",
		)

	def move(self, qty, timestamp, kind="Purchase Receipt", name="P"):
		return frappe._dict(
			qty=qty,
			timestamp=datetime.fromisoformat(timestamp),
			date=timestamp[:10],
			voucher_type=kind,
			voucher_no=name,
		)

	def evaluate(self, weights=None, entries=None):
		return detect(
			self.rule,
			self.batch,
			"House",
			self.moves,
			weights if weights is not None else [self.weight],
			entries or {},
			self.profile,
			"2026-10-23",
		)

	def test_mortality_threshold_boundary_and_both_thresholds(self):
		self.moves.append(self.move(-2, "2026-10-22 12:00:00", "Stock Entry", "DEATH"))
		entries = {"DEATH": frappe._dict(stock_entry_type="Mortality", purpose="Material Issue")}
		self.assertEqual(self.evaluate(entries=entries).state, "Active")
		self.rule.minimum_deaths = 3
		self.assertEqual(self.evaluate(entries=entries).state, "Cleared")
		self.rule.minimum_deaths = 2
		self.rule.mortality_percent = 3
		self.assertEqual(self.evaluate(entries=entries).state, "Cleared")

	def test_mortality_last_completed_day_only(self):
		self.moves.append(self.move(-10, "2026-10-23 12:00:00", "Stock Entry", "TODAY"))
		self.assertEqual(self.evaluate().state, "Cleared")
		self.assertEqual(self.evaluate().evidence_date, "2026-10-22")

	def test_receipts_in_exposure_and_culling_not_deaths(self):
		self.moves[0] = self.move(100, "2026-10-22 07:00:00")
		self.moves.append(self.move(-2, "2026-10-22 12:00:00", "Stock Entry", "CULL"))
		entries = {"CULL": frappe._dict(stock_entry_type="Culling", purpose="Material Issue")}
		self.assertEqual(self.evaluate(entries=entries).state, "Cleared")

	def test_corrections_missing_parents_and_transformations_unknown(self):
		for kind, name, entry in [
			("Stock Reconciliation", "COR", None),
			("Stock Entry", "HIDDEN", None),
			("Stock Entry", "SPLIT", frappe._dict(stock_entry_type="Repack", purpose="Repack")),
		]:
			with self.subTest(kind=kind, name=name):
				self.moves = [*self.moves[:1], self.move(-2, "2026-10-22 12:00:00", kind, name)]
				self.assertEqual(self.evaluate(entries={name: entry} if entry else {}).state, "Unknown")

	def test_empty_exposure_cleared(self):
		self.moves = []
		self.assertEqual(self.evaluate().state, "Cleared")

	def test_growth_measurement_age_threshold_and_missing_target(self):
		self.rule.alert_type = "Below-target Weight"
		self.assertEqual(self.evaluate().state, "Active")
		self.weight.actual_weight = 1.8
		# Use a binary-exact boundary for the at-threshold comparison.
		self.weight.actual_weight = 1.5
		self.rule.weight_shortfall_percent = 25
		self.assertEqual(self.evaluate().state, "Active")
		self.rule.weight_shortfall_percent = 26
		self.assertEqual(self.evaluate().state, "Cleared")
		self.profile.targets = []
		self.assertEqual(self.evaluate().state, "Unknown")

	def test_zero_target_missing_hatch_and_invalid_weights_unknown(self):
		self.rule.alert_type = "Below-target Weight"
		for field, value in [
			("lvm_weight_uom", "g"),
			("sample_size", 0),
			("actual_weight", float("nan")),
			("sample_size", 101),
		]:
			weight = frappe._dict(self.weight)
			weight[field] = value
			self.assertEqual(self.evaluate(weights=[weight]).state, "Unknown")
		self.profile.targets[0].weight_kg = "0"
		self.assertEqual(self.evaluate().state, "Unknown")
		self.batch.lvm_hatch_date = None
		self.assertEqual(self.evaluate().state, "Unknown")

	def test_new_valid_measurement_can_recover_growth(self):
		self.rule.alert_type = "Below-target Weight"
		new = frappe._dict(self.weight, name="W2", posting_date="2026-10-22 08:00:00", actual_weight=2)
		self.profile.targets.append(frappe._dict(age_days=21, weight_kg="2"))
		self.assertEqual(self.evaluate(weights=[self.weight, new]).state, "Cleared")

	def test_weighing_due_is_strictly_after_due_date(self):
		self.rule.alert_type = "Overdue Weighing"
		self.assertEqual(self.evaluate().state, "Cleared")
		self.rule.max_gap_days = 1
		self.assertEqual(self.evaluate().state, "Active")

	def test_never_weighed_arrival_and_reoccupation(self):
		self.rule.alert_type = "Overdue Weighing"
		self.assertEqual(self.evaluate(weights=[]).state, "Active")
		self.moves.extend(
			[
				self.move(-100, "2026-10-20 08:00:00", "Delivery Note", "EXIT"),
				self.move(100, "2026-10-22 07:00:00", name="NEW"),
			]
		)
		self.assertEqual(self.evaluate(weights=[]).state, "Cleared")
		self.assertIsNone(latest_valid_weight([self.weight], self.moves, occupancy(self.moves)[1]))

	def test_repack_does_not_reset_arrival_and_transfer_does(self):
		self.moves.extend(
			[
				self.move(-100, "2026-10-22 08:00:00", "Stock Entry", "REPACK"),
				self.move(100, "2026-10-22 08:00:00", "Stock Entry", "REPACK"),
			]
		)
		self.assertEqual(occupancy(self.moves)[1], datetime(2026, 10, 1, 7))

	def test_empty_house_recovery_and_negative_balance_unknown(self):
		self.rule.alert_type = "Overdue Weighing"
		self.moves.append(self.move(-100, "2026-10-22 08:00:00", "Delivery Note", "EXIT"))
		self.assertEqual(self.evaluate().state, "Cleared")
		self.moves.append(self.move(-1, "2026-10-22 09:00:00", "Delivery Note", "BAD"))
		self.assertEqual(self.evaluate().state, "Unknown")

	def test_pending_diagnosis_end_date_completion_cancellation_and_missing_date(self):
		doc = frappe._dict(name="D", batch="B", docstatus=0, status="Pending", end_date="2026-10-22")
		self.assertEqual(detect_treatment(doc, None, "2026-10-23").state, "Active")
		doc.end_date = "2026-10-23"
		self.assertEqual(detect_treatment(doc, None, "2026-10-23").state, "Cleared")
		doc.end_date = None
		self.assertEqual(detect_treatment(doc, None, "2026-10-23").state, "Unknown")
		for status in ("Completed", "Cancelled"):
			doc.status = status
			self.assertEqual(detect_treatment(doc, None, "2026-10-23").state, "Cleared")
		doc.status = "Pending"
		doc.docstatus = 2
		self.assertEqual(detect_treatment(doc, None, "2026-10-23").state, "Cleared")
