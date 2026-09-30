# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from erpnext.stock.doctype.batch.batch import make_batch
from frappe.model.document import Document


class OffspringRecord(Document):
    def validate(self):
        for row in self.table_zutm:
            item = frappe.get_cached_value(
                "Item",
                row.item,
                ["has_serial_no", "serial_no_series", "is_stock_item", "has_batch_no", "create_new_batch"],
                as_dict=True,
            )

            row.has_serial_no = item.has_serial_no
            row.has_batch_no = item.has_batch_no

            if item.has_batch_no:
                if row.batch_no:
                    batch = frappe.get_cached_doc("Batch", row.batch_no)
                    if batch.item != row.item or batch.disabled:
                        frappe.throw(
                            f"Row {row.idx}: Select an enabled Batch belonging to Item {row.item}."
                        )
                elif not item.create_new_batch:
                    frappe.throw(
                        f"Row {row.idx}: Select a Batch for Item {row.item}, "
                        "or enable Automatically Create New Batch on the Item."
                    )
            else:
                row.batch_no = None

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

        resolved_batches = []
        for offspring in self.table_zutm:
            has_batch_no = frappe.get_cached_value(
                "Item", offspring.item, "has_batch_no"
            )
            batch_no = offspring.batch_no if has_batch_no else None
            if has_batch_no and not batch_no:
                batch_no = make_batch(
                    frappe._dict(
                        {
                            "item": offspring.item,
                            "reference_doctype": self.doctype,
                            "reference_name": self.name,
                        }
                    )
                )

            resolved_batches.append((offspring, batch_no))
            stock_entry.append("items", {
                "item_code": offspring.item,
                "qty": 1,
                "t_warehouse": self.warehouse,
                "use_serial_batch_fields": 1,
                "serial_no": offspring.requested_serial_no,
                "batch_no": batch_no,
            })

        stock_entry.insert()
        stock_entry.submit()
        for offspring, batch_no in resolved_batches:
            if offspring.batch_no != batch_no:
                offspring.db_set("batch_no", batch_no)
