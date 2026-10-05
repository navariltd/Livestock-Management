# Copyright (c) 2026, Navari Limited and Contributors
# See license.txt

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime

from livestock_management.livestock_management.doctype.livestock_event.livestock_event import (
	LivestockEvent,
	get_events,
)

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


class IntegrationTestLivestockEvent(IntegrationTestCase):
	"""
	Integration tests for LivestockEvent.
	Use this class for testing interactions between multiple components.
	"""

	pass


class TestLivestockEventCalendar(TestCase):
	def setUp(self):
		translation = patch(
			"livestock_management.livestock_management.doctype.livestock_event.livestock_event._",
			side_effect=lambda message: message,
		)
		translation.start()
		self.addCleanup(translation.stop)

	def test_missing_end_defaults_to_start(self):
		event = SimpleNamespace(starts_on="2026-10-05 09:00:00", ends_on=None)
		LivestockEvent.validate(event)
		self.assertEqual(event.ends_on, event.starts_on)

	def test_valid_duration_is_preserved(self):
		event = SimpleNamespace(starts_on="2026-10-05 09:00:00", ends_on="2026-10-06 12:00:00")
		LivestockEvent.validate(event)
		self.assertEqual(event.ends_on, "2026-10-06 12:00:00")

	def test_rejects_missing_start_and_reversed_dates(self):
		for start, end in [(None, None), ("2026-10-05 12:00:00", "2026-10-05 09:00:00")]:
			with self.subTest(start=start, end=end):
				with patch.object(frappe, "throw", side_effect=frappe.ValidationError):
					with self.assertRaises(frappe.ValidationError):
						LivestockEvent.validate(SimpleNamespace(starts_on=start, ends_on=end))

	def test_calendar_preserves_filters_and_checks_date_overlap(self):
		user_filters = [["Livestock Event", "serial_no", "=", "COW-1"]]
		with patch.object(frappe, "get_list", return_value=[{"name": "LE-1", "all_day": 1}]) as query:
			result = get_events("2026-10-01", "2026-11-01", user_filters)
		self.assertEqual(result, [{"name": "LE-1", "all_day": 1}])
		self.assertEqual(len(user_filters), 1)
		self.assertEqual(query.call_args.args, ("Livestock Event",))
		args = query.call_args.kwargs
		self.assertNotIn("ignore_permissions", args)
		self.assertIn("all_day", args["fields"])
		self.assertEqual(args["limit_page_length"], 0)
		self.assertEqual(
			args["filters"],
			[
				*user_filters,
				["Livestock Event", "starts_on", "is", "set"],
				["Livestock Event", "starts_on", "<=", get_datetime("2026-11-01")],
				["Livestock Event", "ends_on", ">=", get_datetime("2026-10-01")],
			],
		)

	def test_calendar_accepts_json_filters(self):
		with patch.object(frappe, "get_list", return_value=[]) as query:
			get_events("2026-10-01", "2026-11-01", '[["husbandry", "=", "Pregnancy Check"]]')
		self.assertIn(["husbandry", "=", "Pregnancy Check"], query.call_args.kwargs["filters"])
