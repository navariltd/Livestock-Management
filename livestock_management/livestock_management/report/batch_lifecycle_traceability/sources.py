"""Permission-scoped source collection for lifecycle reporting."""

from collections import defaultdict

import frappe
from frappe.utils import add_days, getdate

from livestock_management.livestock_management.batch_stock import get_batch_movements
from livestock_management.livestock_management.report.batch_lifecycle_traceability.lineage import (
	classify_repack,
	repack_allocations,
	same_allocations,
)

STOCK_FIELDS = [
	"name",
	"purpose",
	"stock_entry_type",
	"lvm_batch",
	"lvm_livestock_house",
	"posting_date",
	"posting_time",
	"is_return",
	"customer",
	"lvm_offspring_record",
	"lvm_source_material_issue",
	"lvm_veterinary_diagnosis",
]
ACTIVITIES = {
	"Weight Record": dict(
		company="lvm_company",
		date="posting_date",
		house="lvm_livestock_house",
		filters={"docstatus": ["<", 2]},
		fields=["actual_weight", "sample_size", "lvm_weight_uom"],
	),
	"Livestock Event": dict(
		company="lvm_company",
		date="starts_on",
		house="lvm_livestock_house",
		filters={"docstatus": ["<", 2], "status": "Completed"},
		fields=["husbandry", "status"],
	),
	"Veterinary Diagnosis": dict(
		company="company",
		date="diagnosis_date",
		house="capitalisation_warehouse",
		filters={"docstatus": 1, "status": "Completed"},
		fields=["medical_stock_entry", "capitalisation_stock_entry", "status", "treatment_type"],
	),
}


class LifecycleSources:
	def __init__(self, filters):
		self.filters = filters
		self.notices = set()
		self.docs = {}
		self.items = {
			r.name: r
			for r in frappe.get_list(
				"Item",
				filters={"is_stock_item": 1, "has_batch_no": 1, "stock_uom": ["in", ["Nos", "Unit"]]},
				fields=["name", "stock_uom"],
				limit_page_length=0,
			)
		}
		self.batches = (
			{
				r.name: r
				for r in frappe.get_list(
					"Batch",
					filters={"item": ["in", list(self.items)]},
					fields=["name", "item"],
					limit_page_length=0,
				)
			}
			if self.items
			else {}
		)
		self.warehouses = set(
			frappe.get_list(
				"Warehouse",
				filters={"company": filters.company, "is_group": 0},
				pluck="name",
				limit_page_length=0,
			)
		)
		# Warehouse and display-date filters must not hide lineage edges.
		self.movements = get_batch_movements(
			dict(company=filters.company, to_date=filters.to_date, item_codes=list(self.items)),
			list(self.batches),
		)
		self.load_stock_documents()
		self.remove_hidden_vouchers()
		self.transformations = self.load_transformations()
		self.offspring = self.load_offspring()
		self.customers = self.load_customers()

	def readable(self, doctype):
		if not frappe.has_permission(doctype, "read"):
			self.notices.add(f"No read access to {doctype}; the lifecycle view is incomplete.")
			return False
		return True

	def load_stock_documents(self):
		vouchers = defaultdict(set)
		for rows in self.movements.values():
			for row in rows:
				vouchers[row.voucher_type].add(row.voucher_no)
		# Header-linked feed/medicine issues have no animal ledger rows.
		vouchers.setdefault("Stock Entry", set())
		for doctype, names in sorted(vouchers.items()):
			if not self.readable(doctype):
				continue
			meta = frappe.get_meta(doctype)
			if not meta.has_field("company") or not meta.has_field("posting_date"):
				self.notices.add(
					"Some stock voucher types lack reliable Company/date scope and are excluded."
				)
				continue
			filters = dict(
				company=self.filters.company, docstatus=1, posting_date=["<=", self.filters.to_date]
			)
			if doctype != "Stock Entry":
				filters["name"] = ["in", sorted(names)]
			if doctype in ("Sales Invoice", "Purchase Invoice"):
				filters["update_stock"] = 1
			fields = [f for f in STOCK_FIELDS if f == "name" or meta.has_field(f)]
			self.docs[doctype] = {
				r.name: r
				for r in frappe.get_list(doctype, filters=filters, fields=fields, limit_page_length=0)
			}

	def remove_hidden_vouchers(self):
		for batch, rows in self.movements.items():
			allowed = [r for r in rows if r.voucher_no in self.docs.get(r.voucher_type, {})]
			if len(allowed) != len(rows):
				self.notices.add(
					"Some stock movements are excluded because their source documents are inaccessible or not submitted."
				)
			self.movements[batch] = allowed

	def load_transformations(self):
		repacks = [d.name for d in self.docs.get("Stock Entry", {}).values() if d.purpose == "Repack"]
		if not repacks:
			return {}
		children = frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": ["in", repacks]},
			fields=[
				"parent",
				"item_code",
				"stock_uom",
				"transfer_qty",
				"s_warehouse",
				"t_warehouse",
				"batch_no",
				"serial_and_batch_bundle",
			],
			limit_page_length=0,
		)
		by_parent, bundles = defaultdict(list), defaultdict(list)
		for row in children:
			by_parent[row.parent].append(row)
		bundle_names = sorted({r.serial_and_batch_bundle for r in children if r.serial_and_batch_bundle})
		if bundle_names:
			# Bundle children are scoped through readable Stock Entry parents, never an unrestricted lookup.
			for row in frappe.get_all(
				"Serial and Batch Entry",
				filters={"parent": ["in", bundle_names]},
				fields=["parent", "batch_no", "qty"],
				limit_page_length=0,
			):
				bundles[row.parent].append(row)
		ledger_by_voucher = defaultdict(lambda: defaultdict(float))
		for batch, movements in self.movements.items():
			for movement in movements:
				if movement.voucher_type == "Stock Entry" and movement.qty:
					ledger_by_voucher[movement.voucher_no][
						(batch, movement.warehouse, "in" if movement.qty > 0 else "out")
					] += abs(movement.qty)
		result = {}
		batch_items = {b: doc.item for b, doc in self.batches.items()}
		for name in repacks:
			allocations, complete = repack_allocations(
				by_parent[name], bundles, self.batches, self.warehouses
			)
			actual = ledger_by_voucher[name]
			complete = complete and same_allocations(allocations, actual)
			result[name] = classify_repack(actual, complete, batch_items)
			if self.docs["Stock Entry"][name].stock_entry_type in ("Capitalisation", "Capitalization"):
				# Cost capitalisation must never manufacture a lineage edge, even for malformed legacy entries.
				result[name] = dict(
					event_type="Capitalisation",
					parents=[],
					children=[],
					evidence="Posted stock",
					notes="Cost capitalisation; no lineage relationship inferred.",
				)
			result[name]["associated_batches"] = sorted({key[0] for key in actual})
		return result

	def load_offspring(self):
		if not self.readable("Offspring Record"):
			return {}
		return {
			r.name: r
			for r in frappe.get_list(
				"Offspring Record",
				filters={
					"company": self.filters.company,
					"docstatus": 1,
					"posting_date": ["<=", self.filters.to_date],
					"warehouse": ["in", sorted(self.warehouses)],
				},
				fields=["name"],
				limit_page_length=0,
			)
		}

	def load_customers(self):
		names = {d.customer for docs in self.docs.values() for d in docs.values() if d.get("customer")}
		if not names or not self.readable("Customer"):
			return set()
		return set(
			frappe.get_list(
				"Customer", filters={"name": ["in", sorted(names)]}, pluck="name", limit_page_length=0
			)
		)

	def activities(self, batches):
		result = {}
		for doctype, config in ACTIVITIES.items():
			if not self.readable(doctype):
				continue
			meta = frappe.get_meta(doctype)
			required = ["batch", config["company"], config["date"], config["house"]]
			if not all(meta.has_field(f) for f in required):
				self.notices.add(f"{doctype} lacks historical scope fields; its activities are excluded.")
				continue
			filters = {
				**config["filters"],
				"batch": ["in", sorted(batches)],
				config["company"]: self.filters.company,
				config["date"]: ["<", add_days(self.filters.to_date, 1)],
			}
			fields = list(dict.fromkeys(["name", *required, *config["fields"]]))
			result[doctype] = []
			for row in frappe.get_list(doctype, filters=filters, fields=fields, limit_page_length=0):
				if getdate(row.get(config["date"])) > self.filters.to_date:
					continue
				house = row.get(config["house"])
				if not house and doctype == "Veterinary Diagnosis":
					medical = self.docs.get("Stock Entry", {}).get(row.medical_stock_entry)
					if medical and medical.lvm_batch == row.batch:
						house = medical.lvm_livestock_house
				if house not in self.warehouses:
					self.notices.add(
						"Activities with missing or inaccessible historical warehouses are excluded."
					)
					continue
				row.lifecycle_house = house
				result[doctype].append(row)
		# Company-null legacy activities cannot be safely assigned by a batch's current location.
		self.notices.add(
			"Legacy activities without an explicit Company or accessible historical warehouse are excluded."
		)
		return result
