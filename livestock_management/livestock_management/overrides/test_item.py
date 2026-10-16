from unittest import TestCase
from unittest.mock import patch

import frappe

from livestock_management.livestock_management.overrides.item import validate


class TestItemCapitalization(TestCase):
	def test_capitalization_requirements(self):
		def raise_validation_error(message):
			raise frappe.ValidationError(message)

		cases = [
			(0, 0, None, None),
			(0, 0, -1, None),
			(1, 0, 30, "Enable Has Batch No"),
			(1, 1, None, "Capitalization Days"),
			(1, 1, 0, "Capitalization Days"),
			(1, 1, -1, "Capitalization Days"),
			(1, 1, 1, None),
			(1, 1, 30, None),
		]
		with patch("livestock_management.livestock_management.overrides.item._", side_effect=lambda s: s):
			with patch("livestock_management.livestock_management.overrides.item.frappe.throw") as throw:
				throw.side_effect = raise_validation_error
				for enabled, batch, days, error in cases:
					with self.subTest(enabled=enabled, batch=batch, days=days):
						doc = frappe._dict(
							lvm_to_capitalize=enabled, has_batch_no=batch, lvm_capitalization_days=days
						)
						if error:
							with self.assertRaisesRegex(frappe.ValidationError, error):
								validate(doc)
						else:
							validate(doc)
