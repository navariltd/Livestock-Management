from contextlib import nullcontext
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.doctype.livestock_performance_alert_rule import (
	livestock_performance_alert_rule as rules,
)
from livestock_management.livestock_management.performance_alerts import data


class TestInputPermissions(TestCase):
	def test_complete_ids_required_not_partial_aggregates(self):
		context = nullcontext()
		with (
			patch.object(data, "as_user", return_value=context),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", return_value=["ONE"]),
		):
			self.assertFalse(
				data.inputs_accessible("farmer@example.com", {"Stock Ledger Entry": {"ONE", "HIDDEN"}})
			)
			self.assertTrue(data.inputs_accessible("farmer@example.com", {"Stock Ledger Entry": {"ONE"}}))

	def test_missing_doctype_permission_is_unknown_input(self):
		with (
			patch.object(data, "as_user", side_effect=lambda user: nullcontext()),
			patch.object(frappe, "has_permission", return_value=False),
			patch.object(frappe, "get_list") as query,
		):
			self.assertFalse(data.inputs_accessible("farmer@example.com", {"Company": {"C"}}))
			query.assert_not_called()

	def test_user_context_restored_on_exception(self):
		with (
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
			patch.object(frappe, "set_user") as change,
		):
			with self.assertRaises(RuntimeError), data.as_user("farmer@example.com"):
				raise RuntimeError("failure")
			self.assertEqual(change.call_args_list[-1].args, ("Administrator",))

	def test_baseline_scopes_company_item_house_and_flagged_batches(self):
		rule = frappe._dict(company="C", item_code="Bird", warehouse="House")
		with (
			patch.object(
				frappe, "get_all", side_effect=[["Bird"], [frappe._dict(name="B", item="Bird")]]
			) as query,
			patch.object(data, "get_batch_movements", return_value={}) as stock,
		):
			data.baseline(rule, "2026-10-23")
			self.assertEqual(query.call_args.kwargs["filters"]["lvm_is_livestock_item"], 1)
			self.assertEqual(stock.call_args.args[0]["warehouse"], "House")
			self.assertEqual(stock.call_args.args[0]["company"], "C")
			self.assertEqual(stock.call_args.args[1], ["B"])

	def test_house_scoped_treatment_unknown_without_explicit_house(self):
		rule = frappe._dict(company="C", warehouse="House", responsible_user="farmer@example.com")
		diagnosis = frappe._dict(name="D", batch="B", status="Pending", docstatus=0, end_date="2026-10-22")
		with (
			patch.object(frappe, "get_all", return_value=[diagnosis]),
			patch.object(data, "inputs_accessible") as permission,
		):
			results = data.treatment_evaluations(rule, {"B": frappe._dict(item="Bird")}, "2026-10-23")
			self.assertEqual(results[0].state, "Unknown")
			permission.assert_not_called()

	def test_treatment_pending_draft_and_completed_both_queried_for_recovery(self):
		rule = frappe._dict(company="C", responsible_user="farmer@example.com")
		rows = [
			frappe._dict(name="P", batch="B", status="Pending", docstatus=0, end_date="2026-10-22"),
			frappe._dict(name="C", batch="B", status="Completed", docstatus=1),
		]
		with (
			patch.object(frappe, "get_all", return_value=rows) as query,
			patch.object(data, "inputs_accessible", return_value=True),
		):
			results = data.treatment_evaluations(
				rule, {"B": frappe._dict(name="B", item="Bird")}, "2026-10-23"
			)
			self.assertEqual([r.state for r in results], ["Active", "Cleared"])
			self.assertNotIn("docstatus", query.call_args.kwargs["filters"])
			self.assertEqual(query.call_args.kwargs["filters"]["company"], "C")


class TestAlertRule(TestCase):
	def test_threshold_validation(self):
		for value in (None, 0, -1, "NaN", "inf", "bad"):
			self.assertFalse(rules.valid_threshold(value, 0, 100))
		self.assertTrue(rules.valid_threshold(2.5, 0, 100))
		self.assertFalse(rules.valid_threshold(2.5, 0, whole=True))
		self.assertTrue(rules.valid_threshold(2, 0, whole=True))

	def test_overlapping_scopes(self):
		self.assertTrue(
			rules.scopes_overlap(frappe._dict(), frappe._dict(item_code="Bird", warehouse="House"))
		)
		self.assertTrue(rules.scopes_overlap(frappe._dict(item_code="Bird"), frappe._dict(warehouse="House")))
		self.assertFalse(rules.scopes_overlap(frappe._dict(item_code="Bird"), frappe._dict(item_code="Cow")))
		self.assertFalse(rules.scopes_overlap(frappe._dict(warehouse="A"), frappe._dict(warehouse="B")))

	def test_enabled_rule_rejects_overlap_and_disabled_rule_needs_no_threshold(self):
		rule = frappe._dict(
			name="R", alert_type="Mortality", company="C", responsible_user="farmer@example.com", enabled=0
		)
		user = Mock(enabled=1, user_type="System User")
		with (
			patch.object(frappe, "get_doc", side_effect=lambda dt, name: user if dt == "User" else Mock()),
			patch.object(
				frappe, "db", Mock(sql=Mock(return_value=[frappe._dict(item_code=None, warehouse=None)]))
			) as db,
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(rules, "_", side_effect=lambda x: x),
		):
			rules.LivestockPerformanceAlertRule.validate(rule)
			db.sql.assert_not_called()
			rule.enabled = 1
			rule.minimum_deaths = 2
			rule.mortality_percent = 2
			with self.assertRaises(frappe.ValidationError):
				rules.LivestockPerformanceAlertRule.validate(rule)
			db.get_value.assert_called_with("Company", "C", "name", for_update=True)

	def test_disabled_or_portal_responsible_user_rejected(self):
		rule = frappe._dict(
			name="R", alert_type="Mortality", company="C", responsible_user="farmer@example.com", enabled=0
		)
		with (
			patch.object(frappe, "get_doc", return_value=Mock(enabled=0, user_type="System User")),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(rules, "_", side_effect=lambda x: x),
			self.assertRaises(frappe.ValidationError),
		):
			rules.LivestockPerformanceAlertRule.validate(rule)
