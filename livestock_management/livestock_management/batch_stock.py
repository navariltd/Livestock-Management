# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

"""Historical batch movements shared by the performance report and population chart."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, getdate


def get_batch_movements(filters, batch_names):
	if not batch_names:
		return {}
	frappe.has_permission("Stock Ledger Entry", "read", throw=True)
	# Ledger permissions alone need not include Warehouse User Permissions.
	warehouses = frappe.get_list(
		"Warehouse", filters={"company": filters["company"], "is_group": 0}, pluck="name", limit_page_length=0
	)
	if filters.get("warehouse"):
		if filters["warehouse"] not in warehouses:
			frappe.throw(_("You cannot access the selected Warehouse."), frappe.PermissionError)
		warehouses = [filters["warehouse"]]
	if not warehouses:
		return {}
	ledger_filters = {
		"company": filters["company"],
		"posting_date": ["<=", filters["to_date"]],
		"is_cancelled": 0,
		"docstatus": ["<", 2],
	}
	if filters.get("item_code"):
		ledger_filters["item_code"] = filters["item_code"]
	elif filters.get("item_codes"):
		ledger_filters["item_code"] = ["in", filters["item_codes"]]
	ledger_filters["warehouse"] = ["in", warehouses]
	ledger = frappe.get_list(
		"Stock Ledger Entry",
		filters=ledger_filters,
		fields=[
			"name",
			"posting_date",
			"posting_time",
			"actual_qty",
			"batch_no",
			"serial_and_batch_bundle",
			"voucher_type",
			"voucher_no",
			"warehouse",
		],
		limit_page_length=0,
	)
	bundles = {d.serial_and_batch_bundle for d in ledger if d.serial_and_batch_bundle}
	bundle_rows = defaultdict(list)
	if bundles:
		for d in frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": ["in", list(bundles)]},
			fields=["parent", "batch_no", "qty"],
			limit_page_length=0,
		):
			bundle_rows[d.parent].append(d)
	movements = defaultdict(list)
	for d in ledger:
		# Bundle quantities already carry the inward/outward sign. Do not also count legacy fields.
		parts = (
			bundle_rows[d.serial_and_batch_bundle]
			if d.serial_and_batch_bundle
			else [frappe._dict(batch_no=d.batch_no, qty=d.actual_qty)]
		)
		for part in parts:
			if part.batch_no in batch_names:
				movements[part.batch_no].append(
					frappe._dict(
						date=getdate(d.posting_date),
						timestamp=get_datetime(f"{d.posting_date} {d.posting_time}"),
						qty=flt(part.qty),
						voucher_type=d.voucher_type,
						voucher_no=d.voucher_no,
						warehouse=d.warehouse,
					)
				)
	return movements
