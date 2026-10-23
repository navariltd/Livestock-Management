from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.performance_alerts import scheduler


class TestDailyScheduler(TestCase):
	def test_non_administrator_cannot_run_scheduler(self):
		with (
			patch.object(frappe, "session", frappe._dict(user="farmer@example.com")),
			patch.object(frappe, "get_all") as query,
		):
			with self.assertRaises(frappe.PermissionError):
				scheduler.run_daily()
			query.assert_not_called()
			self.assertEqual(frappe.session.user, "farmer@example.com")

	def test_concurrent_run_returns_without_processing(self):
		lock = Mock()
		lock.acquire.return_value = False
		with (
			patch.object(frappe, "cache", Mock(lock=Mock(return_value=lock))),
			patch.object(scheduler, "process_rule") as processor,
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
		):
			self.assertEqual(scheduler.run_daily(), {"locked": True})
			processor.assert_not_called()
			lock.release.assert_not_called()

	def test_rules_are_isolated_committed_and_lock_released(self):
		lock = Mock()
		lock.acquire.return_value = True

		def process(rule, today):
			if rule.name == "BAD":
				raise RuntimeError("bad input")
			return {"created": 1}

		with (
			patch.object(frappe, "cache", Mock(lock=Mock(return_value=lock))),
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
			patch.object(scheduler, "nowdate", return_value="2026-10-23"),
			patch.object(frappe, "get_all", return_value=["BAD", "GOOD", "OFF"]),
			patch.object(
				frappe, "get_doc", side_effect=lambda dt, name: frappe._dict(name=name, enabled=name != "OFF")
			),
			patch.object(scheduler, "process_rule", side_effect=process),
			patch.object(scheduler, "mark_unavailable") as unavailable,
			patch.object(frappe, "db", Mock()) as db,
			patch.object(frappe, "log_error"),
			patch.object(frappe, "get_traceback", return_value="error"),
		):
			result = scheduler.run_daily()
			self.assertEqual(result, {"created": 1, "failed_rules": 1})
			db.rollback.assert_called_once()
			self.assertEqual(db.commit.call_count, 2)
			unavailable.assert_called_once_with("BAD")
			lock.release.assert_called_once()
