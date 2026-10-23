"""Complete baseline inputs, checked against the responsible user's permission-filtered view."""

from collections import defaultdict
from contextlib import contextmanager

import frappe
from frappe.utils import add_days, getdate

from livestock_management.livestock_management.batch_stock import get_batch_movements
from livestock_management.livestock_management.performance_alerts.evaluation import (
	Evaluation,
	detect,
	detect_treatment,
	occupancy,
)


@contextmanager
def as_user(user):
	previous = frappe.session.user
	try:
		frappe.set_user(user)
		yield
	finally:
		frappe.set_user(previous)


def inputs_accessible(user, required):
	"""Compare full required IDs, not filtered aggregates that could silently undercount."""
	try:
		with as_user(user):
			for doctype, names in required.items():
				if not names:
					continue
				if not frappe.has_permission(doctype, "read"):
					return False
				allowed = set(
					frappe.get_list(
						doctype, filters={"name": ["in", sorted(names)]}, pluck="name", limit_page_length=0
					)
				)
				if allowed != set(names):
					return False
		return True
	except frappe.PermissionError:
		return False


def baseline(rule, today):
	item_filters = {"is_stock_item": 1, "has_batch_no": 1, "stock_uom": ["in", ["Nos", "Unit"]]}
	if rule.item_code:
		item_filters["name"] = rule.item_code
	items = frappe.get_all("Item", filters=item_filters, pluck="name", limit_page_length=0)
	batches = (
		{
			b.name: b
			for b in frappe.get_all(
				"Batch",
				filters={"lvm_is_livestock_item": 1, "item": ["in", items]},
				fields=["name", "item", "lvm_hatch_date", "lvm_performance_profile"],
				limit_page_length=0,
			)
		}
		if items
		else {}
	)
	moves = get_batch_movements(
		dict(company=rule.company, warehouse=rule.warehouse, to_date=today, item_codes=items), list(batches)
	)
	groups = defaultdict(list)
	for batch, rows in moves.items():
		for move in rows:
			groups[(batch, move.warehouse)].append(move)
	return batches, groups


def required_inputs(rule, batch, house):
	required = defaultdict(set)
	required["Company"].add(rule.company)
	required["Batch"].add(batch.name)
	required["Item"].add(batch.item)
	if house:
		required["Warehouse"].add(house)
	return required


def evaluate_rule(rule, today):
	user = frappe.get_doc("User", rule.responsible_user)
	if not user.enabled or user.user_type != "System User":
		raise frappe.ValidationError("Responsible user must be an enabled System User.")
	batches, groups = baseline(rule, today)
	if rule.alert_type == "Overdue Treatment":
		return treatment_evaluations(rule, batches, today)
	weights = defaultdict(list)
	unknown_house = defaultdict(list)
	profiles = {}
	if rule.alert_type != "Mortality" and batches:
		for weight in frappe.get_all(
			"Weight Record",
			filters={
				"batch": ["in", list(batches)],
				"lvm_company": rule.company,
				"docstatus": ["<", 2],
				"posting_date": ["<", add_days(today, 1)],
			},
			fields=[
				"name",
				"batch",
				"posting_date",
				"actual_weight",
				"sample_size",
				"lvm_weight_uom",
				"lvm_livestock_house",
			],
			limit_page_length=0,
		):
			if weight.lvm_livestock_house:
				weights[(weight.batch, weight.lvm_livestock_house)].append(weight)
			else:
				unknown_house[weight.batch].append(weight)
		if rule.alert_type == "Below-target Weight":
			for name in {b.lvm_performance_profile for b in batches.values() if b.lvm_performance_profile}:
				profile = frappe.get_doc("Livestock Performance Profile", name)
				if profile.docstatus == 1:
					profiles[name] = profile
	stock_entries = {}
	if rule.alert_type == "Mortality":
		vouchers = {
			m.voucher_no
			for rows in groups.values()
			for m in rows
			if m.voucher_type == "Stock Entry" and getdate(m.date) == getdate(add_days(today, -1))
		}
		if vouchers:
			stock_entries = {
				e.name: e
				for e in frappe.get_all(
					"Stock Entry",
					filters={"name": ["in", sorted(vouchers)], "company": rule.company, "docstatus": 1},
					fields=["name", "stock_entry_type", "purpose"],
					limit_page_length=0,
				)
			}
	results = []
	for (batch_name, house), movements in sorted(groups.items()):
		batch = batches[batch_name]
		required = required_inputs(rule, batch, house)
		considered = [
			m for m in movements if rule.alert_type != "Mortality" or getdate(m.date) < getdate(today)
		]
		for move in considered:
			required["Stock Ledger Entry"].add(move.ledger_name)
			required[move.voucher_type].add(move.voucher_no)
		balance, arrival = occupancy(movements)
		scope_weights = weights[(batch_name, house)]
		uncertain = [
			w for w in unknown_house[batch_name] if not arrival or getdate(w.posting_date) >= getdate(arrival)
		]
		if rule.alert_type != "Mortality":
			required["Weight Record"].update(w.name for w in scope_weights)
			if uncertain and balance:
				results.append(
					Evaluation(
						batch_name,
						house,
						"Unknown",
						"A measurement lacks a historical house; weighing scope cannot be established.",
						str(today),
					)
				)
				continue
		profile = profiles.get(batch.lvm_performance_profile)
		if profile and rule.alert_type == "Below-target Weight" and balance:
			required["Livestock Performance Profile"].add(profile.name)
		if not inputs_accessible(rule.responsible_user, required):
			results.append(
				Evaluation(
					batch_name,
					house,
					"Unknown",
					"Responsible user cannot access the complete input scope.",
					str(today),
				)
			)
			continue
		results.append(detect(rule, batch, house, movements, scope_weights, stock_entries, profile, today))
	return results


def treatment_evaluations(rule, batches, today):
	results = []
	if not batches:
		return results
	rows = frappe.get_all(
		"Veterinary Diagnosis",
		filters={"company": rule.company, "batch": ["in", list(batches)]},
		fields=[
			"name",
			"batch",
			"docstatus",
			"status",
			"end_date",
			"capitalisation_warehouse",
			"medical_stock_entry",
		],
		limit_page_length=0,
	)
	for diagnosis in rows:
		house = diagnosis.capitalisation_warehouse
		medical = None
		if not house and diagnosis.medical_stock_entry:
			medical = frappe.get_doc("Stock Entry", diagnosis.medical_stock_entry)
			if medical.company == rule.company and medical.lvm_batch == diagnosis.batch:
				house = medical.lvm_livestock_house
		if rule.warehouse and house != rule.warehouse:
			if not house:
				results.append(
					Evaluation(
						diagnosis.batch,
						None,
						"Unknown",
						"Treatment has no historical house for this House-scoped rule.",
						str(today),
						"Veterinary Diagnosis",
						diagnosis.name,
					)
				)
			continue
		required = required_inputs(rule, batches[diagnosis.batch], house)
		required["Veterinary Diagnosis"].add(diagnosis.name)
		if medical:
			required["Stock Entry"].add(medical.name)
		if house:
			warehouse = frappe.get_doc("Warehouse", house)
			if warehouse.company != rule.company or warehouse.is_group:
				results.append(
					Evaluation(
						diagnosis.batch,
						house,
						"Unknown",
						"Treatment warehouse does not belong to this Company.",
						str(today),
						"Veterinary Diagnosis",
						diagnosis.name,
					)
				)
				continue
		if not inputs_accessible(rule.responsible_user, required):
			results.append(
				Evaluation(
					diagnosis.batch,
					house,
					"Unknown",
					"Responsible user cannot access the treatment follow-up scope.",
					str(today),
					"Veterinary Diagnosis",
					diagnosis.name,
				)
			)
			continue
		results.append(detect_treatment(diagnosis, house, today))
	return results
