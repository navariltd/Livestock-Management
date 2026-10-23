"""Episode history lives on standard ToDos; no separate Alert record is created."""

import json
from contextlib import contextmanager
from hashlib import sha256

import frappe
from frappe import _
from frappe.utils import escape_html, get_url_to_form, now_datetime

META_FIELDS = (
	"lvm_alert_rule",
	"lvm_alert_type",
	"lvm_alert_company",
	"lvm_alert_batch",
	"lvm_alert_house",
	"lvm_alert_scope_key",
	"lvm_alert_condition",
	"lvm_alert_evidence_date",
	"lvm_alert_evaluated_on",
	"lvm_alert_evidence",
	"lvm_alert_recipient_email",
)


@contextmanager
def managed_writes():
	previous = frappe.flags.in_performance_alerts
	frappe.flags.in_performance_alerts = True
	try:
		yield
	finally:
		frappe.flags.in_performance_alerts = previous


def validate_metadata(doc, method=None):
	if frappe.flags.in_performance_alerts:
		return
	before = doc.get_doc_before_save()
	managed = any(doc.get(f) for f in META_FIELDS) or (before and any(before.get(f) for f in META_FIELDS))
	if not managed:
		return
	if doc.is_new() or any(
		doc.get(f) != before.get(f)
		for f in (*META_FIELDS, "reference_type", "reference_name", "allocated_to")
	):
		frappe.throw(
			_(
				"Performance alert metadata and ownership are maintained by the detector. Change the alert rule to change ownership; use status or comments for follow-up."
			)
		)


def scope_key(rule, result):
	# Treatment is an episode on the diagnosis, even if its location is later clarified.
	house = "" if rule.alert_type == "Overdue Treatment" else result.house or ""
	source = result.source_name if rule.alert_type == "Overdue Treatment" else ""
	return sha256(
		json.dumps(
			[rule.company, rule.alert_type, result.batch, house, source], separators=(",", ":")
		).encode()
	).hexdigest()


def choose_todo(records, state):
	"""An acknowledged unresolved episode takes precedence over any historical open task."""
	unresolved = next((r for r in records if r.lvm_alert_condition != "Cleared"), None)
	if unresolved:
		return unresolved
	if state == "Active":
		return next((r for r in records if r.status == "Open"), None)
	return None


def evidence_text(rule, result):
	return f"{rule.alert_type}; Company: {rule.company}; Batch: {result.batch}; House: {result.house or 'Not recorded'}. Evidence date: {result.evidence_date}. {result.summary}"


def apply_evaluation(rule, result, auto_close, today):
	key = scope_key(rule, result)
	records = frappe.get_all(
		"ToDo",
		filters={"lvm_alert_scope_key": key},
		fields=["name", "status", "lvm_alert_condition"],
		order_by="creation desc, name desc",
		limit_page_length=0,
	)
	chosen = choose_todo(records, result.state)
	if not chosen and result.state != "Active":
		return "skipped"
	with managed_writes():
		if not chosen:
			reference_type = "Veterinary Diagnosis" if rule.alert_type == "Overdue Treatment" else "Batch"
			reference_name = result.source_name if reference_type == "Veterinary Diagnosis" else result.batch
			text = evidence_text(rule, result)
			description = escape_html(text)
			if result.source_doctype and result.source_name:
				url = escape_html(get_url_to_form(result.source_doctype, result.source_name))
				description += f'<br><a href="{url}">Open evidence document</a>'
			doc = frappe.get_doc(
				doctype="ToDo",
				status="Open",
				priority="High",
				date=today,
				allocated_to=rule.responsible_user,
				assigned_by=frappe.session.user,
				reference_type=reference_type,
				reference_name=reference_name,
				description=description,
			)
		else:
			doc = frappe.get_doc("ToDo", chosen.name)
		doc.lvm_alert_evaluated_on = now_datetime()
		if result.state == "Unknown":
			# Keep previous evidence/recipient/reference: no new inaccessible information is disclosed.
			doc.lvm_alert_condition = "Unknown"
			doc.save(ignore_permissions=True)
			return "unknown"
		previous = doc.get("lvm_alert_condition")
		doc.update(
			dict(
				lvm_alert_rule=rule.name,
				lvm_alert_type=rule.alert_type,
				lvm_alert_company=rule.company,
				lvm_alert_batch=result.batch,
				lvm_alert_house=result.house,
				lvm_alert_scope_key=key,
				lvm_alert_condition=result.state,
				lvm_alert_evidence_date=result.evidence_date,
				lvm_alert_evidence=evidence_text(rule, result),
			)
		)
		created = doc.is_new()
		if result.state == "Active":
			doc.allocated_to = rule.responsible_user
			doc.lvm_alert_recipient_email = frappe.db.get_value("User", rule.responsible_user, "email")
			# An acknowledged episode stays closed until a confirmed recovery, even across further breaches.
		else:
			if doc.status == "Open" and auto_close:
				doc.status = "Closed"
		doc.save(ignore_permissions=True)
		if previous == "Cleared" and result.state == "Active":
			doc.add_comment("Info", "Condition recurred; existing open performance follow-up reused.")
		elif previous != "Cleared" and result.state == "Cleared":
			doc.add_comment("Info", "Performance condition cleared: " + escape_html(result.summary))
		return "created" if created else "updated"


def mark_unavailable(rule_name, seen_keys=()):
	"""Missing scopes/configuration are not evidence of recovery."""
	count = 0
	with managed_writes():
		for row in frappe.get_all(
			"ToDo",
			filters={"lvm_alert_rule": rule_name, "lvm_alert_condition": ["in", ["Active", "Unknown"]]},
			fields=["name", "lvm_alert_scope_key"],
			limit_page_length=0,
		):
			if row.lvm_alert_scope_key in seen_keys:
				continue
			doc = frappe.get_doc("ToDo", row.name)
			doc.lvm_alert_condition = "Unknown"
			doc.lvm_alert_evaluated_on = now_datetime()
			doc.save(ignore_permissions=True)
			count += 1
	return count


def prevent_history_deletion(doc, method=None):
	if (
		doc.get("lvm_alert_scope_key")
		and not frappe.flags.in_performance_alerts
		and not frappe.flags.in_uninstall
	):
		frappe.throw(_("Close or cancel this performance ToDo instead of deleting its episode history."))
