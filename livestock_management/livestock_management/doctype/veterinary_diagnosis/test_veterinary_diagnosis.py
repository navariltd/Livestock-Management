# Copyright (c) 2026, Navari Limited and Contributors
# See license.txt

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.query_builder.builder import MariaDB
from pypika.dialects import MySQLQueryBuilder

from livestock_management.livestock_management.doctype.veterinary_diagnosis import veterinary_diagnosis
from livestock_management.livestock_management.overrides import stock_entry


class Row(frappe._dict):
	def __getattribute__(self, name):
		if name == "items" and "items" in self:
			return self["items"]
		return super().__getattribute__(name)

	def precision(self, fieldname):
		return 2


def make_stock_entry(name="MED-1"):
	entry = Row(name=name, docstatus=1, items=[], additional_costs=[])
	entry.insert = Mock()
	entry.submit = Mock()
	entry.reload = Mock()
	entry.cancel = Mock()
	entry.append = lambda table, values: entry[table].append(Row(values))
	return entry


class TestVeterinaryDiagnosisStock(TestCase):
	def setUp(self):
		database = patch.object(frappe, "db", Mock())
		database.start()
		self.addCleanup(database.stop)
		for mock in (
			patch.object(frappe, "get_system_settings", return_value=None),
			patch.object(veterinary_diagnosis, "nowtime", return_value="12:00:00"),
		):
			mock.start()
			self.addCleanup(mock.stop)
		for module in (veterinary_diagnosis, stock_entry):
			translation = patch.object(module, "_", side_effect=lambda message: message)
			translation.start()
			self.addCleanup(translation.stop)
		throw = patch.object(frappe, "throw", side_effect=frappe.ValidationError)
		throw.start()
		self.addCleanup(throw.stop)
		self.doc = object.__new__(veterinary_diagnosis.VeterinaryDiagnosis)
		self.doc.__dict__.update(
			doctype="Veterinary Diagnosis",
			name="VD-1",
			company="Farm",
			status="Completed",
			posting_date="2026-10-06",
			start_date="2026-10-01",
			end_date=None,
			to_capitalize=0,
			treatment_plans=[
				Row(idx=1, item="Medicine", qty=2, warehouse="Stores", batch_no=None, serial_no=None)
			],
			purchase_invoices=[],
		)
		self.doc.db_set = Mock()
		self.doc.precision = lambda fieldname: 2
		self.item = Row(
			is_stock_item=1, disabled=0, has_batch_no=0, has_serial_no=0, stock_uom="Nos", is_fixed_asset=0
		)
		self.warehouse = Row(company="Farm", is_group=0)

	def test_completed_status_required(self):
		for status in ("Pending", "Cancelled"):
			with self.subTest(status=status), self.assertRaises(frappe.ValidationError):
				self.doc.status = status
				self.doc.before_submit()

	def test_no_medicines_rejected(self):
		self.doc.treatment_plans = []
		with self.assertRaises(frappe.ValidationError):
			self.doc.before_submit()

	def test_completed_dates_propagate(self):
		with (
			patch.object(veterinary_diagnosis, "nowdate", return_value="2026-10-06"),
			patch.object(frappe, "get_cached_value", return_value="KES"),
		):
			self.doc.validate()
		self.assertEqual(self.doc.end_date, "2026-10-06")
		self.assertEqual(self.doc.treatment_plans[0].start_date, "2026-10-01")
		self.assertEqual(self.doc.treatment_plans[0].end_date, "2026-10-06")

	def test_treatment_stock_validation(self):
		with (
			patch.object(frappe, "get_cached_doc", return_value=self.item),
			patch.object(frappe, "get_doc", return_value=self.warehouse),
		):
			self.doc.validate_treatment_stock()
			for qty in (0, -1, None):
				with self.subTest(qty=qty), self.assertRaises(frappe.ValidationError):
					self.doc.treatment_plans[0].qty = qty
					self.doc.validate_treatment_stock()

	def test_invalid_medicine_and_warehouse_rejected(self):
		for item_changes, warehouse_changes in (
			({"is_stock_item": 0}, {}),
			({"disabled": 1}, {}),
			({}, {"company": "Other"}),
			({}, {"is_group": 1}),
		):
			with (
				self.subTest(item=item_changes, warehouse=warehouse_changes),
				patch.object(frappe, "get_cached_doc", return_value=Row(self.item | item_changes)),
				patch.object(frappe, "get_doc", return_value=Row(self.warehouse | warehouse_changes)),
				self.assertRaises(frappe.ValidationError),
			):
				self.doc.validate_treatment_stock()

	def test_required_medicine_tracking_rejected(self):
		for flag in ("has_batch_no", "has_serial_no"):
			with (
				self.subTest(flag=flag),
				patch.object(frappe, "get_cached_doc", return_value=Row(self.item | {flag: 1})),
				patch.object(frappe, "get_doc", return_value=self.warehouse),
				self.assertRaises(frappe.ValidationError),
			):
				self.doc.validate_treatment_stock()

	def test_medical_entry_uses_stock_uom_and_tracking(self):
		self.item.update(has_batch_no=1, has_serial_no=1)
		self.doc.treatment_plans[0].update(batch_no="MED-BATCH", serial_no="MED-SERIAL-1\nMED-SERIAL-2")
		entry = make_stock_entry()
		with (
			patch.object(frappe, "new_doc", return_value=entry),
			patch.object(frappe, "get_cached_doc", return_value=self.item),
			patch.object(frappe.db, "get_value", return_value="Treatment Expense") as get_account,
			patch.object(self.doc, "validate_expense_account") as validate_account,
		):
			self.assertIs(self.doc.create_medical_entry(), entry)
		get_account.assert_called_once_with("Company", "Farm", "lvm_treatment_stock_entry_difference_account")
		validate_account.assert_called_once_with("Treatment Expense")
		self.assertEqual((entry.stock_entry_type, entry.purpose), ("Medical", "Material Issue"))
		self.assertEqual(entry.lvm_veterinary_diagnosis, "VD-1")
		self.assertEqual(entry.items[0].qty, 2)
		self.assertEqual(entry.items[0].uom, "Nos")
		self.assertEqual(entry.items[0].conversion_factor, 1)
		self.assertEqual(entry.items[0].s_warehouse, "Stores")
		self.assertEqual(entry.items[0].batch_no, "MED-BATCH")
		self.assertEqual(entry.items[0].serial_no, "MED-SERIAL-1\nMED-SERIAL-2")
		entry.insert.assert_called_once()
		entry.submit.assert_called_once()
		entry.reload.assert_called_once()

	def test_optional_capitalisation_and_total(self):
		medical = make_stock_entry()
		medical.total_outgoing_value = 120
		medical.items = [Row(expense_account="Medicine Expense", amount=120)]
		self.doc.purchase_invoices = [Row(purchase_invoice="PI-1", cost=30, expense_account="Vet Expense")]
		for enabled in (0, 1):
			self.doc.to_capitalize = enabled
			self.doc.db_set.reset_mock()
			with (
				patch.object(frappe.db, "get_value"),
				patch.object(self.doc, "get_generated_entry", return_value=None),
				patch.object(self.doc, "create_medical_entry", return_value=medical),
				patch.object(
					veterinary_diagnosis, "create_repack_entry", return_value=Row(name="CAP-1")
				) as repack,
			):
				self.doc.on_submit()
			self.doc.db_set.assert_any_call("total_medical_cost", 150, update_modified=False)
			self.doc.db_set.assert_any_call("medical_stock_entry", "MED-1", update_modified=False)
			if enabled:
				costs = repack.call_args.kwargs["additional_costs"]
				self.assertEqual([row["amount"] for row in costs], [120, 30])
				self.assertEqual(
					[row["expense_account"] for row in costs], ["Medicine Expense", "Vet Expense"]
				)
				self.doc.db_set.assert_any_call("capitalisation_stock_entry", "CAP-1", update_modified=False)
			else:
				repack.assert_not_called()

	def test_submission_retry_does_not_duplicate_stock(self):
		self.doc.to_capitalize = 1
		with (
			patch.object(frappe.db, "get_value"),
			patch.object(
				self.doc,
				"get_generated_entry",
				side_effect=[Row(name="MED-1", total_outgoing_value=120), Row(name="CAP-1")],
			),
			patch.object(self.doc, "create_medical_entry") as medical,
			patch.object(veterinary_diagnosis, "create_repack_entry") as repack,
		):
			self.doc.on_submit()
		medical.assert_not_called()
		repack.assert_not_called()

	def test_draft_generated_entry_is_not_reused(self):
		with (
			patch.object(frappe.db, "get_value", return_value="MED-1"),
			patch.object(frappe, "get_doc", return_value=Row(docstatus=0)),
			self.assertRaises(frappe.ValidationError),
		):
			self.doc.get_generated_entry("Medical")

	def test_failed_capitalisation_propagates_without_committing(self):
		self.doc.to_capitalize = 1
		medical = Row(name="MED-1", total_outgoing_value=120, items=[])
		with (
			patch.object(self.doc, "get_generated_entry", return_value=None),
			patch.object(self.doc, "create_medical_entry", return_value=medical),
			patch.object(veterinary_diagnosis, "create_repack_entry", side_effect=frappe.ValidationError),
			self.assertRaises(frappe.ValidationError),
		):
			self.doc.on_submit()
		frappe.db.commit.assert_not_called()

	def test_invoice_allocation_query_uses_a_locking_read(self):
		queries = []

		def run(query):
			queries.append(query.get_sql())
			return [(12,), (8,)]

		with patch.object(frappe, "qb", MariaDB), patch.object(MySQLQueryBuilder, "run", run):
			self.assertEqual(self.doc.get_allocated_invoice_cost("PI-1", "Vet Expense"), 20)
		self.assertIn("FOR UPDATE", queries[0])
		self.assertIn("`docstatus`=1", queries[0])
		self.assertIn("`to_capitalize`=1", queries[0])
		self.assertIn("`name`<>'VD-1'", queries[0])

	def test_cancellation_locks_invoice_allocations_in_stable_order(self):
		self.doc.purchase_invoices = [Row(purchase_invoice=name) for name in ("PI-2", "PI-1", "PI-2")]
		self.doc.before_cancel()
		self.assertEqual([call.args[1] for call in frappe.db.get_value.call_args_list], ["PI-1", "PI-2"])
		self.assertTrue(all(call.kwargs["for_update"] for call in frappe.db.get_value.call_args_list))

	def test_cancel_reverses_capitalisation_before_consumption(self):
		capitalisation, medical = make_stock_entry("CAP-1"), make_stock_entry("MED-1")
		order = []
		capitalisation.cancel.side_effect = lambda: order.append("CAP-1")
		medical.cancel.side_effect = lambda: order.append("MED-1")
		with patch.object(self.doc, "get_generated_entry", side_effect=[capitalisation, medical]) as lookup:
			self.doc.on_cancel()
		self.assertEqual(order, ["CAP-1", "MED-1"])
		self.assertEqual([call.args[0] for call in lookup.call_args_list], ["Capitalisation", "Medical"])
		self.assertNotIn("ignore_linked_doctypes", medical)

	def test_invoice_allocation_limits_exclude_stock_and_fixed_assets(self):
		self.doc.to_capitalize = 1
		self.doc.purchase_invoices = [
			Row(idx=1, purchase_invoice="PI-1", expense_account="Vet Expense", cost=30)
		]
		invoice = Row(
			docstatus=1,
			company="Farm",
			is_return=0,
			check_permission=Mock(),
			items=[
				Row(item_code="Service", expense_account="Vet Expense", base_net_amount=50),
				Row(item_code="Medicine", expense_account="Vet Expense", base_net_amount=100),
				Row(item_code="Asset", expense_account="Vet Expense", base_net_amount=100),
				Row(
					item_code="Service",
					expense_account="Vet Expense",
					base_net_amount=100,
					enable_deferred_expense=1,
				),
			],
		)
		items = {
			"Service": Row(is_stock_item=0, is_fixed_asset=0),
			"Medicine": Row(is_stock_item=1, is_fixed_asset=0),
			"Asset": Row(is_stock_item=0, is_fixed_asset=1),
		}
		with (
			patch.object(frappe, "get_doc", return_value=invoice) as get_doc,
			patch.object(frappe, "get_cached_doc", side_effect=lambda dt, name: items[name]),
			patch.object(self.doc, "validate_expense_account"),
			patch.object(self.doc, "get_allocated_invoice_cost", return_value=20),
		):
			self.doc.validate_purchase_invoice_costs()
			get_doc.assert_called_once_with("Purchase Invoice", "PI-1", for_update=True)
			invoice.check_permission.assert_called_once_with("read")
			self.doc.purchase_invoices[0].cost = 31
			with self.assertRaises(frappe.ValidationError):
				self.doc.validate_purchase_invoice_costs()

	def test_duplicate_invoice_rows_share_one_allocation_limit(self):
		self.doc.purchase_invoices = [
			Row(idx=idx, purchase_invoice="PI-1", expense_account="Vet Expense", cost=30) for idx in (1, 2)
		]
		invoice = Row(
			docstatus=1,
			company="Farm",
			is_return=0,
			check_permission=Mock(),
			items=[Row(item_code=None, expense_account="Vet Expense", base_net_amount=50)],
		)
		with (
			patch.object(frappe, "get_doc", return_value=invoice),
			patch.object(self.doc, "validate_expense_account"),
			self.assertRaises(frappe.ValidationError),
		):
			self.doc.validate_purchase_invoice_costs()

	def test_invalid_invoices_and_nonpositive_costs_rejected(self):
		self.doc.purchase_invoices = [
			Row(idx=1, purchase_invoice="PI-1", expense_account="Vet Expense", cost=30)
		]
		for overrides in ({"docstatus": 0}, {"docstatus": 2}, {"company": "Other"}, {"is_return": 1}):
			invoice = Row(
				{"docstatus": 1, "company": "Farm", "is_return": 0, "check_permission": Mock()} | overrides
			)
			with (
				self.subTest(overrides=overrides),
				patch.object(frappe, "get_doc", return_value=invoice),
				patch.object(self.doc, "validate_expense_account"),
				self.assertRaises(frappe.ValidationError),
			):
				self.doc.validate_purchase_invoice_costs()
		for cost in (0, -1):
			self.doc.purchase_invoices[0].cost = cost
			with self.assertRaises(frappe.ValidationError):
				self.doc.validate_purchase_invoice_costs()

	def test_expense_account_company_currency_and_ledger_validation(self):
		valid = Row(company="Farm", is_group=0, disabled=0, root_type="Expense", account_currency="KES")
		for overrides in (
			{},
			{"company": "Other"},
			{"is_group": 1},
			{"disabled": 1},
			{"root_type": "Asset"},
			{"account_currency": "USD"},
		):
			with (
				patch.object(frappe, "get_doc", return_value=Row(valid | overrides)),
				patch.object(frappe, "get_cached_value", return_value="KES"),
			):
				if overrides:
					with self.assertRaises(frappe.ValidationError):
						self.doc.validate_expense_account("Expense")
				else:
					self.doc.validate_expense_account("Expense")


class TestLivestockCapitalisation(TestCase):
	def setUp(self):
		translation = patch.object(stock_entry, "_", side_effect=lambda message: message)
		translation.start()
		self.addCleanup(translation.stop)
		throw = patch.object(frappe, "throw", side_effect=frappe.ValidationError)
		throw.start()
		self.addCleanup(throw.stop)

	def test_repack_uses_warehouse_batch_quantity_and_not_medicine_rate(self):
		source = Row(
			name="MED-1",
			stock_entry_type="Medical",
			company="Farm",
			lvm_batch="ANIMAL-BATCH",
			posting_date="2026-10-06",
			posting_time="12:00:00",
			items=[Row(expense_account="Expense", amount=120)],
		)
		target = Row(
			item_code="Livestock",
			warehouse="Farm Warehouse",
			batch_no="ANIMAL-BATCH",
			qty=None,
			serial_no=None,
		)
		repack = make_stock_entry("CAP-1")
		with (
			patch.object(stock_entry, "get_capitalisation_target", return_value=target),
			patch.object(stock_entry, "get_batch_qty", return_value=3) as quantity,
			patch.object(frappe, "new_doc", return_value=repack),
		):
			result = stock_entry.create_repack_entry(source, Row(basic_rate=999))
		self.assertIs(result, repack)
		self.assertEqual((repack.stock_entry_type, repack.purpose), ("Capitalisation", "Repack"))
		self.assertEqual(repack.lvm_source_material_issue, "MED-1")
		self.assertEqual([row.qty for row in repack.items], [3, 3])
		self.assertEqual(repack.items[1].is_finished_item, 1)
		self.assertTrue(all("basic_rate" not in row for row in repack.items))
		self.assertEqual(repack.additional_costs[0].amount, 120)
		self.assertEqual(quantity.call_args.kwargs["warehouse"], "Farm Warehouse")
		self.assertEqual(quantity.call_args.kwargs["posting_date"], "2026-10-06")

	def test_serial_target_repack_preserves_serial_and_batch(self):
		source = Row(name="MED-1", company="Farm", posting_date="2026-10-06", posting_time="12:00:00")
		target = Row(
			item_code="Cow", warehouse="Farm Warehouse", batch_no="COW-BATCH", serial_no="COW-1", qty=1
		)
		repack = make_stock_entry("CAP-1")
		with (
			patch.object(stock_entry, "get_capitalisation_target", return_value=target),
			patch.object(stock_entry, "get_batch_qty") as quantity,
			patch.object(frappe, "new_doc", return_value=repack),
		):
			stock_entry.create_repack_entry(
				source, serial_no="COW-1", additional_costs=[{"amount": 30, "expense_account": "Vet Expense"}]
			)
		quantity.assert_not_called()
		self.assertEqual([row.serial_no for row in repack.items], ["COW-1", "COW-1"])
		self.assertEqual([row.batch_no for row in repack.items], ["COW-BATCH", "COW-BATCH"])
		self.assertEqual([row.qty for row in repack.items], [1, 1])

	def test_no_available_batch_stock_rejected(self):
		with (
			patch.object(
				stock_entry,
				"get_capitalisation_target",
				return_value=Row(
					qty=None, batch_no="BATCH", warehouse="Farm Warehouse", item_code="Livestock"
				),
			),
			patch.object(stock_entry, "get_batch_qty", return_value=0),
			self.assertRaises(frappe.ValidationError),
		):
			stock_entry.create_repack_entry(
				Row(company="Farm", posting_date="2026-10-06", posting_time="12:00:00")
			)

	def test_target_selection_and_consistency(self):
		serial = Row(company="Farm", warehouse="Farm Warehouse", item_code="Cow", batch_no="COW-BATCH")
		batch = Row(item="Cow", disabled=0, lvm_location="Farm Warehouse")
		warehouse = Row(company="Farm", is_group=0)
		item = Row(is_stock_item=1, disabled=0, has_serial_no=1, has_batch_no=1)

		def get_doc(doctype, name):
			return {"Serial No": serial, "Batch": batch, "Warehouse": warehouse}[doctype]

		with (
			patch.object(frappe, "get_doc", side_effect=get_doc),
			patch.object(frappe, "get_cached_doc", return_value=item),
		):
			target = stock_entry.get_capitalisation_target("Farm", serial_no="COW-1")
			self.assertEqual((target.qty, target.batch_no, target.serial_no), (1, "COW-BATCH", "COW-1"))
			for kwargs in (
				{},
				{"batch_no": "COW-BATCH"},
				{"serial_no": "COW-1", "batch_no": "WRONG"},
				{"serial_no": "COW-1", "warehouse": "Other Warehouse"},
			):
				with self.subTest(kwargs=kwargs), self.assertRaises(frappe.ValidationError):
					stock_entry.get_capitalisation_target("Farm", **kwargs)

	def test_medical_issue_does_not_trigger_generic_capitalisation(self):
		with patch.object(stock_entry, "create_repack_entry") as repack:
			stock_entry.on_submit_livestock_entry(
				Row(purpose="Material Issue", stock_entry_type="Medical"), None
			)
		repack.assert_not_called()

	def test_generic_hook_preserves_active_batch_capitalisation(self):
		for entry_type in ("Feeding", "Treatment"):
			for status in ("Active", "Closed"):
				with (
					self.subTest(entry_type=entry_type, status=status),
					patch.object(frappe, "get_doc", return_value=Row(lvm_capitalisation_status=status)),
					patch.object(stock_entry, "create_repack_entry") as repack,
				):
					stock_entry.on_submit_livestock_entry(
						Row(
							purpose="Material Issue",
							stock_entry_type=entry_type,
							lvm_batch="ANIMAL-BATCH",
							items=[Row(amount=120)],
						),
						None,
					)
					self.assertEqual(repack.call_count, int(status == "Active"))

	def test_generic_hook_skips_missing_livestock_batch(self):
		with patch.object(stock_entry, "create_repack_entry") as repack:
			stock_entry.on_submit_livestock_entry(
				Row(purpose="Material Issue", stock_entry_type="Treatment", items=[Row(amount=120)]), None
			)
		repack.assert_not_called()

	def test_material_issue_costs_retain_multiple_accounts(self):
		costs = stock_entry.get_material_issue_costs(
			Row(
				stock_entry_type="Medical",
				name="MED-1",
				items=[
					Row(expense_account="A", amount=20),
					Row(expense_account="B", amount=30),
					Row(expense_account="A", amount=40),
				],
			)
		)
		self.assertEqual({row["expense_account"]: row["amount"] for row in costs}, {"A": 60, "B": 30})


class TestStockEntryDifferenceAccounts(TestCase):
	def test_accounts_follow_entry_company_and_type(self):
		fields = {
			"Feeding": "lvm_feeding_stock_entry_difference_account",
			"Treatment": "lvm_treatment_stock_entry_difference_account",
			"Medical": "lvm_treatment_stock_entry_difference_account",
			"Capitalisation": "lvm_capitalisation_stock_entry_difference_account",
			"Egg Production": "lvm_egg_production_stock_entry_difference_account",
			"Mortality": "lvm_mortality_stock_entry_difference_account",
		}
		for company in ("Farm", "Other Farm"):
			for entry_type, field in fields.items():
				with (
					self.subTest(company=company, entry_type=entry_type),
					patch.object(frappe, "db", Mock()) as db,
				):
					db.get_value.return_value = company + " Expense"
					doc = Row(company=company, stock_entry_type=entry_type, items=[Row(), Row()])
					stock_entry.before_save_livestock_entry(doc, None)
					db.get_value.assert_called_once_with("Company", company, field)
					self.assertTrue(all(row.expense_account == company + " Expense" for row in doc.items))

	def test_unconfigured_or_unrelated_entries_keep_existing_account(self):
		for entry_type in ("Feeding", "Material Transfer"):
			with self.subTest(entry_type=entry_type), patch.object(frappe, "db", Mock()) as db:
				db.get_value.return_value = None
				doc = Row(
					company="Farm", stock_entry_type=entry_type, items=[Row(expense_account="Existing")]
				)
				stock_entry.before_save_livestock_entry(doc, None)
				self.assertEqual(doc.items[0].expense_account, "Existing")
				if entry_type == "Material Transfer":
					db.get_value.assert_not_called()
