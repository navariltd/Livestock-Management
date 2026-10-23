"""Daily detection with one scheduler lock and a separate transaction per rule."""

from collections import Counter

import frappe
from frappe.utils import getdate, nowdate

from livestock_management.livestock_management.performance_alerts.data import evaluate_rule
from livestock_management.livestock_management.performance_alerts.todos import (
	apply_evaluation,
	mark_unavailable,
	scope_key,
)


def process_rule(rule, today):
	results = evaluate_rule(rule, today)
	auto_close = bool(frappe.db.get_value("Company", rule.company, "lvm_auto_close_performance_todos"))
	counts = Counter()
	seen = set()
	for result in results:
		seen.add(scope_key(rule, result))
		counts[apply_evaluation(rule, result, auto_close, today)] += 1
	missing = mark_unavailable(rule.name, seen)
	unknown = sum(r.state == "Unknown" for r in results) + missing
	if unknown:
		frappe.log_error(
			title="Performance alert inputs unavailable",
			message=f"Rule {rule.name}: {unknown} scope(s) have missing, invalid, or inaccessible inputs. No recovery was inferred.\n"
			+ "\n".join(
				f"{r.batch} / {r.house or 'unspecified house'}: {r.summary}"
				for r in results
				if r.state == "Unknown"
			),
		)
	return dict(counts)


def run_daily():
	# Frappe scheduled jobs already run as Administrator; never elevate a caller.
	if frappe.session.user != "Administrator":
		raise frappe.PermissionError("Performance alert scheduling requires Administrator.")
	lock = frappe.cache.lock("livestock-performance-alerts", timeout=3600)
	if not lock.acquire(blocking=False):
		return {"locked": True}
	counts = Counter()
	try:
		today = getdate(nowdate())
		for name in frappe.get_all(
			"Livestock Performance Alert Rule", filters={"enabled": 1}, pluck="name", limit_page_length=0
		):
			try:
				rule = frappe.get_doc("Livestock Performance Alert Rule", name)
				# Skip a rule disabled since the initial list was read.
				if not rule.enabled:
					continue
				counts.update(process_rule(rule, today))
				frappe.db.commit()
			except Exception:
				frappe.db.rollback()
				failure = frappe.get_traceback()
				try:
					mark_unavailable(name)
				except Exception:
					frappe.db.rollback()
					failure += "\nUnable to mark existing tasks Unknown:\n" + frappe.get_traceback()
				frappe.log_error(
					title="Performance alert rule failed",
					message=f"Rule {name}\n{failure}",
				)
				frappe.db.commit()
				counts["failed_rules"] += 1
	finally:
		lock.release()
	return dict(counts)
