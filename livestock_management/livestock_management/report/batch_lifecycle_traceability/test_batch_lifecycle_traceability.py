from datetime import datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.utils import getdate

from livestock_management.livestock_management.report.batch_lifecycle_traceability import (
	batch_lifecycle_traceability as report,
)


class TestLifecycleEvents(TestCase):
	def setUp(self):
		self.sources = SimpleNamespace(
			batches={"A": frappe._dict(item="Bird"), "B": frappe._dict(item="Bird")},
			items={"Bird": frappe._dict(stock_uom="Nos")},
			docs={"Stock Entry": {}},
			movements={},
			transformations={},
			customers={"Allowed Customer"},
			offspring={"BIRTH": {}},
			warehouses={"House", "Other"},
			notices=set(),
		)
		for mock in (
			patch.object(report, "_", side_effect=lambda x: x),
			patch.object(report, "nowdate", return_value="2026-10-23"),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
		):
			mock.start()
			self.addCleanup(mock.stop)

	def move(self, qty, warehouse="House", voucher="ENTRY", kind="Stock Entry", day=1):
		return frappe._dict(
			qty=qty,
			warehouse=warehouse,
			voucher_no=voucher,
			voucher_type=kind,
			timestamp=datetime(2026, 10, day, 12),
		)

	def stock(self, **kwargs):
		return frappe._dict(
			name="ENTRY",
			purpose="Material Receipt",
			stock_entry_type="Material Receipt",
			posting_date="2026-10-01",
			posting_time="12:00:00",
			**kwargs,
		)

	def test_purchase_receipt_and_birth_link(self):
		self.sources.docs["Purchase Receipt"] = {"PR": self.stock()}
		self.sources.movements = {"A": [self.move(100, voucher="PR", kind="Purchase Receipt")]}
		rows = report.stock_events(self.sources, {"A"}, {})
		self.assertEqual(rows[0]["event_type"], "Receipt")
		self.sources.docs["Stock Entry"] = {"ENTRY": self.stock(lvm_offspring_record="BIRTH")}
		self.sources.movements = {"A": [self.move(100)]}
		row = report.stock_events(self.sources, {"A"}, {})[0]
		self.assertEqual(row["event_type"], "Birth")
		self.assertEqual(row["reference_name"], "BIRTH")
		self.sources.offspring = {}
		self.assertEqual(report.stock_events(self.sources, {"A"}, {})[0]["event_type"], "Receipt")

	def test_transfer_preserves_both_sides_and_bundle_allocations_aggregate_once(self):
		doc = self.stock()
		doc.purpose = "Material Transfer"
		self.sources.docs["Stock Entry"] = {"ENTRY": doc}
		self.sources.movements = {"A": [self.move(-60), self.move(-40), self.move(100, "Other")]}
		rows = report.stock_events(self.sources, {"A"}, {})
		self.assertEqual(len(rows), 2)
		self.assertEqual({r["event_type"] for r in rows}, {"Transfer"})
		self.assertEqual(sum(r["qty_in"] for r in rows), 100)
		self.assertEqual(sum(r["qty_out"] for r in rows), 100)

	def test_mortality_culling_reconciliation_sales_and_returns(self):
		for kind, document, expected in [
			(
				"Stock Entry",
				frappe._dict(purpose="Material Issue", stock_entry_type="Mortality"),
				"Mortality",
			),
			("Stock Entry", frappe._dict(purpose="Material Issue", stock_entry_type="Culling"), "Culling"),
			("Stock Reconciliation", frappe._dict(), "Correction"),
			("Delivery Note", frappe._dict(is_return=0), "Sale"),
			("Sales Invoice", frappe._dict(is_return=1), "Customer return"),
			("Purchase Receipt", frappe._dict(is_return=1), "Supplier return"),
		]:
			with self.subTest(kind=kind, expected=expected):
				self.assertEqual(report.stock_event_type(kind, document, 0, 10), expected)

	def test_sale_hides_inaccessible_customer(self):
		self.sources.docs["Delivery Note"] = {"DN": self.stock(customer="Hidden Customer")}
		self.sources.movements = {"A": [self.move(-5, voucher="DN", kind="Delivery Note")]}
		self.assertIsNone(report.stock_events(self.sources, {"A"}, {})[0]["customer"])
		self.sources.docs["Delivery Note"]["DN"].customer = "Allowed Customer"
		self.assertEqual(report.stock_events(self.sources, {"A"}, {})[0]["customer"], "Allowed Customer")

	def test_repack_evidence_and_links(self):
		doc = self.stock()
		doc.purpose = "Repack"
		self.sources.docs["Stock Entry"] = {"ENTRY": doc}
		self.sources.movements = {"A": [self.move(-100)], "B": [self.move(100)]}
		self.sources.transformations = {
			"ENTRY": dict(
				event_type="Batch replacement",
				parents=["A"],
				children=["B"],
				evidence="Inferred from Repack",
				notes="Inferred",
			)
		}
		row = report.stock_events(self.sources, {"A"}, {})[0]
		self.assertEqual(row["child_batch_names"], ["B"])
		self.assertEqual(row["related_batch_names"], ["B"])
		self.assertEqual(row["evidence"], "Inferred from Repack")

	def test_ambiguous_associations_are_not_parent_links(self):
		doc = self.stock()
		doc.purpose = "Repack"
		self.sources.docs["Stock Entry"] = {"ENTRY": doc}
		self.sources.movements = {"A": [self.move(-100)]}
		self.sources.transformations = {
			"ENTRY": dict(
				event_type="Ambiguous transformation",
				parents=[],
				children=[],
				associated_batches=["A", "B"],
				evidence="Not inferred",
				notes="Incomplete",
			)
		}
		row = report.stock_events(self.sources, {"A"}, {})[0]
		self.assertEqual(row["related_batch_names"], ["B"])
		self.assertEqual(row["parent_batch_names"], [])

	def test_linked_feed_and_medicine_have_no_animal_quantity_and_no_duplicates(self):
		doc = self.stock(lvm_batch="A", lvm_livestock_house="House", lvm_veterinary_diagnosis="VET")
		doc.purpose = "Material Issue"
		doc.stock_entry_type = "Medical"
		self.sources.docs["Stock Entry"] = {"ENTRY": doc}
		activities = {"Veterinary Diagnosis": [frappe._dict(name="VET")]}
		row = report.linked_stock_events(self.sources, {"A"}, [], activities)[0]
		self.assertIsNone(row["qty_out"])
		self.assertEqual(row["reference_name"], "VET")
		self.assertEqual(row["event_type"], "Treatment")
		self.assertEqual(report.linked_stock_events(self.sources, {"A"}, [row], activities), [])
		doc.stock_entry_type = "Feeding"
		self.assertEqual(report.linked_stock_events(self.sources, {"A"}, [], {})[0]["event_type"], "Feeding")
		doc.lvm_livestock_house = "Hidden"
		self.assertEqual(report.linked_stock_events(self.sources, {"A"}, [], {}), [])

	def test_weight_husbandry_and_completed_treatment_have_actual_timestamps(self):
		activities = {
			"Weight Record": [
				frappe._dict(
					name="W",
					batch="A",
					posting_date="2026-10-02 09:00:00",
					actual_weight=1.5,
					sample_size=10,
					lvm_weight_uom="Kg",
					lifecycle_house="House",
				)
			],
			"Livestock Event": [
				frappe._dict(
					name="H",
					batch="A",
					starts_on="2026-10-01 08:00:00",
					status="Completed",
					husbandry="Vaccination",
					lifecycle_house="House",
				)
			],
			"Veterinary Diagnosis": [
				frappe._dict(
					name="D",
					batch="A",
					diagnosis_date="2026-10-03",
					status="Completed",
					treatment_type="Medical",
					lifecycle_house="House",
				)
			],
		}
		rows = report.activity_events(self.sources, activities)
		self.assertEqual({r["event_type"] for r in rows}, {"Weighing", "Husbandry", "Treatment"})
		self.assertTrue(all(r["qty_in"] is None for r in rows))
		self.assertEqual(next(r for r in rows if r["source_name"] == "H")["timestamp"], "2026-10-01 08:00:00")

	def test_display_filters_and_deterministic_order(self):
		rows = [
			report.base_event(self.sources, "A", "Weight Record", name, "2026-10-02", type_, house)
			for name, type_, house in [
				("Z", "Weighing", "House"),
				("A", "Weighing", "House"),
				("H", "Husbandry", "Other"),
			]
		]
		filters = frappe._dict(
			from_date=getdate("2026-10-02"),
			to_date=getdate("2026-10-02"),
			warehouse="House",
			event_type="Weighing",
		)
		self.assertEqual([r["source_name"] for r in report.filter_events(rows, filters)], ["A", "Z"])
		filters.from_date = getdate("2026-10-03")
		self.assertEqual(report.filter_events(rows, filters), [])

	def test_filter_validation_checks_company_batch_item_and_warehouse(self):
		item = Mock(is_stock_item=1, has_batch_no=1, stock_uom="Nos")
		batch = Mock(item="Bird")
		house = Mock(company="Farm", is_group=0)
		with patch.object(frappe, "get_doc", side_effect=[Mock(), batch, item, house]):
			filters = report.validate_filters(
				dict(company="Farm", batch="A", to_date="2026-10-01", warehouse="House")
			)
			self.assertEqual(filters.include_related_batches, 1)
			batch.check_permission.assert_called_once_with("read")
			house.check_permission.assert_called_once_with("read")

	def test_permission_failure_stops_loading_sources(self):
		with (
			patch.object(report, "validate_filters", return_value=frappe._dict()),
			patch.object(frappe, "has_permission", side_effect=frappe.PermissionError),
			patch.object(report, "LifecycleSources") as loader,
		):
			with self.assertRaises(frappe.PermissionError):
				report.execute({})
			loader.assert_not_called()

	def test_related_history_is_discovered_before_display_filters(self):
		self.sources.transformations = {
			"R": dict(
				parents=["A"],
				children=["B"],
				event_type="Batch replacement",
				evidence="Inferred from Repack",
				notes="Inferred",
			)
		}
		self.sources.activities = Mock(
			return_value={
				"Weight Record": [
					frappe._dict(
						name="W-B",
						batch="B",
						posting_date="2026-10-02 09:00:00",
						actual_weight=1,
						sample_size=10,
						lvm_weight_uom="Kg",
						lifecycle_house="Other",
					)
				]
			}
		)
		filters = frappe._dict(
			company="Farm",
			batch="A",
			include_related_batches=1,
			from_date=getdate("2026-10-02"),
			to_date=getdate("2026-10-03"),
			warehouse="Other",
			event_type="Weighing",
		)
		with (
			patch.object(report, "validate_filters", return_value=filters),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(report, "LifecycleSources", return_value=self.sources),
		):
			_columns, rows, _message = report.execute(filters)
			self.assertEqual([r["batch"] for r in rows], ["B"])
			self.sources.activities.assert_called_once_with({"A", "B"})

	def test_invalid_date_range_and_event_type_fail_before_querying(self):
		for filters in [
			dict(company="Farm", batch="A", to_date="2026-10-24"),
			dict(company="Farm", batch="A", from_date="2026-10-03", to_date="2026-10-02"),
			dict(company="Farm", batch="A", to_date="2026-10-01", event_type="Unknown"),
		]:
			with (
				self.subTest(filters=filters),
				patch.object(frappe, "get_doc") as query,
				self.assertRaises(frappe.ValidationError),
			):
				report.validate_filters(filters)
			query.assert_not_called()
