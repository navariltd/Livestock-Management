# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters: dict | None = None):
    """Return columns and data for the report.

    This is the main entry point for the report. It accepts the filters as a
    dictionary and should return columns and data. It is called by the framework
    every time the report is refreshed or a filter is updated.
    """
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)

    return columns, data


def execute_snapshot_report(filters: dict | None = None):
    """Return columns and data for the report.

    This is the main entry point for snapshot report. When 'Synced
    Report' is enabled in report, framework will call this method
    every time the report is refreshed or a filter is updated. It
    accepts the same filters as normal execute. But a utility method -
    get_latest_sync, is also imported.

    """
    from frappe.database.duckdb.database import get_latest_sync

    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns() -> list[dict]:
    """Return columns for the report.

    One field definition per column, just like a DocType field definition.
    """
    return [
        {
            "label": _("#"),
            "fieldname": "row_index",
            "fieldtype": "Data",
            "width": 60,
        },
        {
            "label": _("Repack Entry"),
            "fieldname": "repack_entry",
            "fieldtype": "link",
            "options": "Stock Entry",
        },
        {
            "label": _("Posting Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
        },
        {
            "label": _("Item"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
        },
        {
            "label": _("Source Warehouse"),
            "fieldname": "s_warehouse",
            "fieldtype": "link",
            "options": "Warehouse",
        },
        {
            "label": _("Target Warehouse"),
            "fieldname": "t_warehouse",
            "fieldtype": "link",
            "options": "Warehouse",
        },
        {
            "label": _("Quantity"),
            "fieldname": "qty",
            "fieldtype": "Float",
        },
        {
            "label": _("Valuation Rate"),
            "fieldname": "valuation_rate",
            "fieldtype": "Currency",
        },
        {
            "label": _("Selling Price"),
            "fieldname": "selling_price",
            "fieldtype": "Currency",
        },
        {
            "label": _("Total Valuation"),
            "fieldname": "total_valuation",
            "fieldtype": "Currency",
        },
        {
            "label": _("Total Selling"),
            "fieldname": "total_selling",
            "fieldtype": "Currency",
        },
        {
            "label": _("Profit"),
            "fieldname": "profit",
            "fieldtype": "Currency",
        },
        {
            "label": _("Opportunity Forgone"),
            "fieldname": "opportunity_forgone",
            "fieldtype": "Currency",
        },
    ]


def get_data(filters: frappe._dict) -> list[dict]:
    conditions = [
        "se.stock_entry_type = 'Capitalisation'",
        "se.docstatus = 1",
    ]
    params = {"selling_price_list": None}

    if filters.get("company"):
        conditions.append("se.company = %(company)s")
        params["company"] = filters.company
    if filters.get("from_date"):
        conditions.append("se.posting_date >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("se.posting_date <= %(to_date)s")
        params["to_date"] = filters.to_date
    if filters.get("repack_entry"):
        conditions.append("se.name = %(repack_entry)s")
        params["repack_entry"] = filters.repack_entry

    price_list = filters.get("selling_price_list") or frappe.db.get_single_value(
        "Selling Settings", "selling_price_list"
    )
    params["selling_price_list"] = price_list

    entries = frappe.db.sql(
        f"""
			SELECT
				se.name AS repack_entry,
				se.posting_date,
				se.posting_time,
				sed.idx,
				sed.item_code,
				sed.s_warehouse,
				sed.t_warehouse,
				sed.qty,
				sed.valuation_rate,
				COALESCE(
					(
						SELECT ip.price_list_rate
						FROM `tabItem Price` ip
						WHERE ip.item_code = sed.item_code
							AND ip.price_list = %(selling_price_list)s
							AND ip.selling = 1
							AND (ip.valid_from IS NULL OR ip.valid_from <= se.posting_date)
							AND (ip.valid_upto IS NULL OR ip.valid_upto >= se.posting_date)
						ORDER BY ip.valid_from DESC, ip.creation DESC
						LIMIT 1
					),
					0
				) AS selling_price
			FROM `tabStock Entry` se
			INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
			WHERE {" AND ".join(conditions)}
				AND (sed.s_warehouse IS NOT NULL OR sed.t_warehouse IS NOT NULL)
			ORDER BY se.posting_date DESC, se.posting_time DESC, se.name DESC, sed.idx
		""",
        params,
        as_dict=True,
    )

    if not entries:
        return []

    entries_by_repack = {}
    for entry in entries:
        entries_by_repack.setdefault(entry.repack_entry, []).append(entry)

    data = []
    for entry_index, (repack_entry, details) in enumerate(
        entries_by_repack.items(), start=1
    ):
        source_profit = sum(
            (detail.selling_price * detail.qty) - (detail.valuation_rate * detail.qty)
            for detail in details
            if detail.s_warehouse
        )
        destination_profit = sum(
            (detail.selling_price * detail.qty) - (detail.valuation_rate * detail.qty)
            for detail in details
            if detail.t_warehouse
        )
        parent_index = str(entry_index)

        data.append(
            {
                "row_index": parent_index,
                "repack_entry": repack_entry,
                "posting_date": details[0].posting_date,
                "opportunity_forgone": source_profit - destination_profit,
                "indent": 0,
                "is_group": 1,
            }
        )

        for detail_index, detail in enumerate(details, start=1):
            total_selling = detail.selling_price * detail.qty
            total_valuation = detail.valuation_rate * detail.qty
            data.append(
                {
                    "row_index": f"{parent_index}.{detail_index}",
                    "parent_row_index": parent_index,
                    "repack_entry": repack_entry,
                    "posting_date": detail.posting_date,
                    "item_code": detail.item_code,
                    "s_warehouse": detail.s_warehouse,
                    "t_warehouse": detail.t_warehouse,
                    "qty": detail.qty,
                    "valuation_rate": detail.valuation_rate,
                    "selling_price": detail.selling_price,
                    "total_valuation": total_valuation,
                    "total_selling": total_selling,
                    "profit": total_selling - total_valuation,
                    "indent": 1,
                }
            )

    return data
