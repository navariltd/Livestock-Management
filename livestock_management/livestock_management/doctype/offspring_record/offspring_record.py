# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OffspringRecord(Document):
    def validate(self):
        for row in self.table_zutm:
            item = frappe.get_cached_value(
                "Item",
                row.item,
                ["has_serial_no", "serial_no_series", "is_stock_item"],
                as_dict=True,
            )

            row.has_serial_no = item.has_serial_no

            if item.has_serial_no and not (
                item.serial_no_series or row.requested_serial_no
            ):
                frappe.throw(
                    f"Row {row.idx}: Enter a serial number for item {row.item}, "
                    "or configure a Serial No Series on the Item."
                )

    def on_submit(self):
        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.stock_entry_type = "Material Receipt"
        stock_entry.purpose = "Material Receipt"
        stock_entry.company = self.company
        stock_entry.posting_date = self.posting_date

        for offspring in self.table_zutm:
            stock_entry.append("items", {
                "item_code": offspring.item,
                "qty": 1,
                "t_warehouse": self.warehouse,
                "use_serial_batch_fields": 1,
                "serial_no": offspring.requested_serial_no,
            })

        stock_entry.insert()
        stock_entry.submit()
        self.db_set("stock_entry", stock_entry.name)
