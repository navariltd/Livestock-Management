from contextlib import nullcontext
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.performance_alerts import todos
from livestock_management.livestock_management.performance_alerts.evaluation import Evaluation


class MemoryToDo(frappe._dict):
	def is_new(self):
		return not self.get("name")

	def save(self, **kwargs):
		self.name = self.get("name") or "TODO"
		return self

	def add_comment(self, *args):
		self.comment = args


class TestToDoEpisodes(TestCase):
	def setUp(self):
		self.rule = frappe._dict(
			name="R", company="C", alert_type="Mortality", responsible_user="farmer@example.com"
		)
		self.result = Evaluation("B", "House", "Active", "Evidence", "2026-10-22", "Batch", "B")
		for mock in (
			patch.object(todos, "managed_writes", side_effect=nullcontext),
			patch.object(todos, "now_datetime", return_value="2026-10-23 00:00:00"),
			patch.object(todos, "get_url_to_form", return_value="https://example.com/app/batch/B"),
		):
			mock.start()
			self.addCleanup(mock.stop)

	def apply(self, result, doc=None, auto_close=False):
		rows = (
			[frappe._dict(name="T", status=doc.status, lvm_alert_condition=doc.lvm_alert_condition)]
			if doc
			else []
		)
		created = []

		def get_doc(*args):
			if len(args) == 1:
				new = MemoryToDo(args[0])
				created.append(new)
				return new
			return doc

		with (
			patch.object(frappe, "get_all", return_value=rows),
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(frappe, "db", Mock(get_value=Mock(return_value="farmer@example.com"))),
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
		):
			action = todos.apply_evaluation(self.rule, result, auto_close, "2026-10-23")
		return action, created

	def test_new_issue_creates_high_priority_assigned_todo(self):
		action, created = self.apply(self.result)
		self.assertEqual(action, "created")
		self.assertEqual(created[0].priority, "High")
		self.assertEqual(created[0].reference_type, "Batch")
		self.assertEqual(created[0].allocated_to, "farmer@example.com")
		self.assertEqual(created[0].lvm_alert_condition, "Active")

	def test_repeat_updates_without_duplicate_and_preserves_manual_description(self):
		doc = MemoryToDo(name="T", status="Open", lvm_alert_condition="Active", description="My notes")
		action, created = self.apply(self.result, doc)
		self.assertEqual(action, "updated")
		self.assertEqual(created, [])
		self.assertEqual(doc.description, "My notes")

	def test_acknowledged_episode_stays_closed_until_recovery(self):
		doc = MemoryToDo(name="T", status="Closed", lvm_alert_condition="Active")
		self.apply(self.result, doc)
		self.assertEqual(doc.status, "Closed")
		self.assertEqual(doc.lvm_alert_condition, "Active")

	def test_recovery_respects_company_setting(self):
		cleared = Evaluation("B", "House", "Cleared", "Recovered", "2026-10-23")
		for auto in (False, True):
			doc = MemoryToDo(name="T", status="Open", lvm_alert_condition="Active")
			self.apply(cleared, doc, auto)
			self.assertEqual(doc.status, "Closed" if auto else "Open")
			self.assertEqual(doc.lvm_alert_condition, "Cleared")

	def test_recurrence_after_closed_recovery_creates_new_todo(self):
		closed = frappe._dict(name="T", status="Closed", lvm_alert_condition="Cleared")
		self.assertIsNone(todos.choose_todo([closed], "Active"))
		closed.status = "Open"
		self.assertIs(todos.choose_todo([closed], "Active"), closed)

	def test_unknown_never_closes_or_overwrites_evidence(self):
		doc = MemoryToDo(
			name="T",
			status="Open",
			lvm_alert_condition="Active",
			lvm_alert_evidence="Known",
			allocated_to="old@example.com",
		)
		unknown = Evaluation("B", "House", "Unknown", "HIDDEN SECRET", "2026-10-23")
		self.apply(unknown, doc, auto_close=True)
		self.assertEqual(doc.status, "Open")
		self.assertEqual(doc.lvm_alert_evidence, "Known")
		self.assertEqual(doc.allocated_to, "old@example.com")
		self.assertEqual(doc.lvm_alert_condition, "Unknown")
		self.assertEqual(self.apply(unknown)[0], "skipped")

	def test_keys_separate_alert_types_but_keep_treatment_key_when_house_changes(self):
		first = todos.scope_key(self.rule, self.result)
		self.rule.alert_type = "Below-target Weight"
		self.assertNotEqual(first, todos.scope_key(self.rule, self.result))
		self.rule.alert_type = "Overdue Treatment"
		a = Evaluation("B", None, "Active", "", "2026-10-23", "Veterinary Diagnosis", "D")
		b = Evaluation("B", "House", "Active", "", "2026-10-23", "Veterinary Diagnosis", "D")
		self.assertEqual(todos.scope_key(self.rule, a), todos.scope_key(self.rule, b))

	def test_metadata_hook_allows_status_but_rejects_source_and_state_changes(self):
		before = frappe._dict(lvm_alert_scope_key="key", lvm_alert_condition="Active", reference_name="B")
		doc = MemoryToDo(before)
		doc.get_doc_before_save = lambda: before
		doc.status = "Closed"
		with (
			patch.object(frappe, "flags", frappe._dict()),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(todos, "_", side_effect=lambda x: x),
		):
			doc.name = "T"
			todos.validate_metadata(doc)
			doc.lvm_alert_condition = "Cleared"
			with self.assertRaises(frappe.ValidationError):
				todos.validate_metadata(doc)

	def test_managed_history_cannot_be_deleted_and_ordinary_tasks_are_unchanged(self):
		with (
			patch.object(frappe, "flags", frappe._dict()),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(todos, "_", side_effect=lambda x: x),
		):
			todos.prevent_history_deletion(frappe._dict())
			with self.assertRaises(frappe.ValidationError):
				todos.prevent_history_deletion(frappe._dict(lvm_alert_scope_key="key"))

	def test_mark_unavailable_preserves_state_and_reports_missing_scope_count(self):
		doc = MemoryToDo(name="T", status="Open", lvm_alert_condition="Active", lvm_alert_evidence="Known")
		rows = [frappe._dict(name="T", lvm_alert_scope_key="missing")]
		with (
			patch.object(frappe, "get_all", return_value=rows),
			patch.object(frappe, "get_doc", return_value=doc),
		):
			self.assertEqual(todos.mark_unavailable("RULE", seen_keys={"seen"}), 1)
			self.assertEqual(doc.status, "Open")
			self.assertEqual(doc.lvm_alert_condition, "Unknown")
			self.assertEqual(doc.lvm_alert_evidence, "Known")
