from datetime import date, datetime
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from livestock_management.livestock_management.report.livestock_batch_performance_report import (
	livestock_batch_performance_report as report,
)


class TestBatchPerformance(TestCase):
	def setUp(self):
		self.translation = patch.object(report, "_", side_effect=lambda text: text)
		self.translation.start()
		self.addCleanup(self.translation.stop)
		self.filters = frappe._dict(from_date=date(2026, 10, 1), to_date=date(2026, 10, 10))
		self.batch = frappe._dict(
			name="FLOCK", manufacturing_date=date(2026, 8, 1), lvm_hatch_date=date(2026, 9, 1)
		)
		self.item = frappe._dict(name="BIRD", stock_uom="Nos")

	def movement(self, day, qty, voucher="RECEIPT", kind="Purchase Receipt"):
		return frappe._dict(
			date=date(2026, 10, day),
			timestamp=datetime(2026, 10, day, 12),
			qty=qty,
			warehouse="HOUSE",
			voucher_no=voucher,
			voucher_type=kind,
		)

	def opening(self):
		return frappe._dict(
			date=date(2026, 9, 30),
			timestamp=datetime(2026, 9, 30),
			qty=100,
			warehouse="HOUSE",
			voucher_no="OPEN",
			voucher_type="Purchase Receipt",
		)

	def row(self, moves, weights=None, operations=None, details=None, entries=None):
		return report.build_row(
			self.batch,
			self.item,
			moves,
			weights or [],
			operations or [],
			details or {},
			entries or {},
			self.filters,
		)

	def test_historical_balance_and_period_mortality(self):
		moves = [self.opening(), self.movement(3, -5, "DEATH", "Stock Entry")]
		row = self.row(moves, entries={"DEATH": frappe._dict(stock_entry_type="Mortality")})
		self.assertEqual(row["opening_qty"], 100)
		self.assertEqual(row["live_qty"], 95)
		self.assertEqual(row["mortality_qty"], 5)
		self.assertEqual(row["survival_percent"], 95)
		self.assertEqual(row["age_days"], 39)

	def test_sales_are_not_deaths_and_survival_is_unavailable(self):
		row = self.row([self.opening(), self.movement(4, -20, kind="Delivery Note")])
		self.assertEqual(row["live_qty"], 80)
		self.assertEqual(row["mortality_qty"], 0)
		self.assertIsNone(row["survival_percent"])

	def test_same_batch_repack_does_not_inflate_movements(self):
		row = self.row(
			[
				self.opening(),
				self.movement(4, -100, "REPACK", "Stock Entry"),
				self.movement(4, 100, "REPACK", "Stock Entry"),
			]
		)
		self.assertEqual(row["incoming_qty"], 0)
		self.assertEqual(row["outgoing_qty"], 0)
		self.assertEqual(row["live_qty"], 100)

	def test_feed_conversion_and_recorded_interval_fcr(self):
		weights = [
			frappe._dict(
				name="W1",
				posting_date=datetime(2026, 10, 1),
				actual_weight=1,
				sample_size=10,
				batch="FLOCK",
				lvm_weight_uom="Kg",
				lvm_livestock_house="HOUSE",
			),
			frappe._dict(
				name="W2",
				posting_date=datetime(2026, 10, 10),
				actual_weight=2,
				sample_size=10,
				batch="FLOCK",
				lvm_weight_uom="Kg",
				lvm_livestock_house="HOUSE",
			),
		]
		entry = frappe._dict(
			name="FEED",
			lvm_batch="FLOCK",
			lvm_livestock_house="HOUSE",
			stock_entry_type="Feeding",
			purpose="Material Issue",
			posting_date=date(2026, 10, 5),
			posting_time="12:00:00",
		)
		detail = frappe._dict(
			parent="FEED", item_code="FEED", transfer_qty=200, stock_uom="Kg", s_warehouse="STORE"
		)
		row = self.row([self.opening()], weights, [entry], {"FEED": [detail]})
		self.assertEqual(row["feed_kg"], 200)
		self.assertEqual(row["fcr"], 2)
		weights[-1].lvm_weight_uom = None
		self.assertIsNone(self.row([self.opening()], weights, [entry], {"FEED": [detail]})["fcr"])

	def test_house_filter_does_not_guess_missing_house_consumption(self):
		self.filters.warehouse = "HOUSE"
		entry = frappe._dict(
			name="FEED", lvm_batch="FLOCK", stock_entry_type="Feeding", purpose="Material Issue"
		)
		row = self.row([self.opening()], operations=[entry])
		self.assertIsNone(row["feed_kg"])
		self.assertIsNone(row["produce_qty"])

	def test_feed_conversion_requires_valid_factor(self):
		with patch.object(frappe, "db", Mock(get_value=Mock(return_value=50))):
			self.assertEqual(report.to_kg("FEED", "g", 100), 2)
		with patch.object(frappe, "db", Mock(get_value=Mock(return_value=None))):
			self.assertIsNone(report.to_kg("FEED", "Bag", 10))

	def test_hatch_date_never_falls_back_to_manufacturing_date(self):
		self.batch.lvm_hatch_date = None
		self.assertIsNone(self.row([self.opening()])["age_days"])

	def test_latest_invalid_unit_does_not_get_used_as_kg(self):
		weight = frappe._dict(
			name="W",
			batch="FLOCK",
			posting_date="2026-10-02",
			actual_weight=1500,
			sample_size=10,
			lvm_weight_uom="g",
			lvm_livestock_house="HOUSE",
		)
		row = self.row([self.opening()], weights=[weight])
		self.assertIsNone(row["actual_weight"])
		self.assertIsNone(row["fcr"])

	def test_house_filter_includes_known_house_and_excludes_other_house(self):
		self.filters.warehouse = "HOUSE"
		entries = [
			frappe._dict(
				name=name,
				lvm_batch="FLOCK",
				lvm_livestock_house=house,
				stock_entry_type="Feeding",
				purpose="Material Issue",
				posting_date="2026-10-02",
				posting_time="12:00:00",
			)
			for name, house in [("F1", "HOUSE"), ("F2", "OTHER")]
		]
		details = {
			e.name: [
				frappe._dict(
					parent=e.name, item_code="FEED", transfer_qty=10, stock_uom="Kg", s_warehouse="STORE"
				)
			]
			for e in entries
		}
		row = self.row([self.opening()], operations=entries, details=details)
		self.assertEqual(row["feed_kg"], 10)

	def test_only_configured_eggs_count_and_stock_quantity_is_not_converted_twice(self):
		self.batch.lvm_hatch_date = self.filters.from_date
		profile = frappe._dict(
			name="P",
			all_female_laying_flock=1,
			egg_items=[frappe._dict(item="EGG"), frappe._dict(item="CRACKED")],
			targets=[frappe._dict(age_days=i, feed_g="100", egg_yield_percent="80") for i in range(10)],
		)
		entry = frappe._dict(
			name="PRODUCE",
			lvm_batch="FLOCK",
			lvm_livestock_house="HOUSE",
			stock_entry_type="Produce Collection",
			purpose="Material Receipt",
			posting_date="2026-10-02",
			posting_time="12:00:00",
		)
		details = [
			frappe._dict(
				parent=entry.name,
				item_code=item,
				transfer_qty=qty,
				qty=1,
				stock_uom="Nos",
				t_warehouse="STORE",
			)
			for item, qty in [("EGG", 30), ("CRACKED", 5), ("OTHER", 10)]
		]
		row = report.build_row(
			self.batch,
			self.item,
			[self.opening()],
			[],
			[entry],
			{entry.name: details},
			{},
			self.filters,
			profile,
		)
		self.assertEqual(row["egg_count"], 35)
		self.assertEqual(row["hen_day_yield"], 3.5)
		self.assertEqual(row["produce_qty"], 45)
		self.assertEqual(row["target_feed_kg"], 100)

	def test_inaccessible_details_do_not_return_partial_totals(self):
		entry = frappe._dict(
			name="F",
			lvm_batch="FLOCK",
			lvm_livestock_house="HOUSE",
			stock_entry_type="Feeding",
			purpose="Material Issue",
			inaccessible_details=True,
		)
		row = self.row(
			[self.opening()],
			operations=[entry],
			details={
				"F": [
					frappe._dict(
						parent="F", item_code="FEED", transfer_qty=10, stock_uom="Kg", s_warehouse="STORE"
					)
				]
			},
		)
		self.assertIsNone(row["feed_kg"])
		self.assertIsNone(row["fcr"])

	def test_queries_scope_company_and_submitted_operations_and_hide_profiles(self):
		self.filters.update(company="COMPANY", item_code="BIRD")
		self.batch.lvm_performance_profile = "PRIVATE"

		def query(doctype, **kwargs):
			if doctype == "Batch":
				return [self.batch]
			if doctype == "Warehouse":
				return ["HOUSE", "STORE"]
			return []

		with (
			patch.object(frappe, "get_list", side_effect=query) as get_list,
			patch.object(
				frappe,
				"has_permission",
				side_effect=lambda dt, *args, **kw: dt != "Livestock Performance Profile",
			),
			patch.object(report, "get_batch_movements", return_value={"FLOCK": [self.opening()]}),
			patch.object(frappe, "get_doc") as get_doc,
		):
			rows = report.get_data(self.filters, self.item)
			self.assertIsNone(rows[0]["performance_profile"])
			get_doc.assert_not_called()
			calls = {call.args[0]: call.kwargs for call in get_list.call_args_list}
			self.assertEqual(calls["Stock Entry"]["filters"]["company"], "COMPANY")
			self.assertEqual(calls["Stock Entry"]["filters"]["docstatus"], 1)
			self.assertEqual(calls["Weight Record"]["filters"]["lvm_company"], "COMPANY")
			self.assertEqual(calls["Weight Record"]["filters"]["docstatus"], ["<", 2])
