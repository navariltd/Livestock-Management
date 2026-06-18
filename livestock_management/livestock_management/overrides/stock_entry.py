import frappe

def on_submit_livestock_entry(doc, method):
    """
    Handle Stock Entry submissions for Feeding and Treatment,
    creating repack entries for active batch capitalisation.
    """
    if doc.purpose == "Material Issue" and doc.stock_entry_type in ["Feeding", "Treatment"]:
        if not doc.items:
            return

        for item in doc.items:
            batch = frappe.get_doc("Batch", doc.lvm_batch)
            if batch.get("lvm_capitalisation_status") == "Active":
                create_repack_entry(doc, item)
                break

def create_repack_entry(source_doc, item_row):
    """
    Create and submit a repack Stock Entry for a qualifying feed or treatment batch.
    """
    repack_doc = frappe.new_doc("Stock Entry")
    repack_doc.stock_entry_type = "Repack"
    repack_doc.purpose = "Material Transfer for Manufacture"
    repack_doc.company = source_doc.company

    # 1. Fetch Expense Account from the first item of the source document
    first_item = source_doc.items[0]
    expense_account = first_item.get("expense_account")

    # 2. Get batch location for warehouse settings
    batch_doc = frappe.get_doc("Batch", source_doc.lvm_batch)
    warehouse = batch_doc.get("lvm_location")
    batch_qty = batch_doc.get("batch_qty")

    if not warehouse:
        frappe.throw(f"Batch {source_doc.lvm_batch} does not have a defined Location/Warehouse.")

    # 3. Add to Additional Costs
    repack_doc.append("additional_costs", {
        "description": f"Capitalizing {source_doc.stock_entry_type} for batch {source_doc.lvm_batch}",
        "amount": source_doc.total_outgoing_value, # Use total outgoing value
        "expense_account": expense_account
    })

    # 4. Append two rows: Raw Material (s_warehouse) and Finished Good (t_warehouse)
    # Row 1: Source (Raw Material)
    repack_doc.append("items", {
        "item_code": item_row.item_code,
        "batch_no": item_row.batch_no,
        "s_warehouse": warehouse,
        "qty": batch_qty,  # Use the batch quantity for the source row
        "basic_rate": item_row.basic_rate,
        "use_serial_batch_fields": 1
    })

    # Row 2: Target (Finished Good)
    repack_doc.append("items", {
        "item_code": item_row.item_code,
        "batch_no": item_row.batch_no,
        "t_warehouse": warehouse,
        "qty": batch_qty,  # Use the batch quantity for the target row
        "basic_rate": item_row.basic_rate,
        "is_finished_item": 1,
        "use_serial_batch_fields": 1
    })

    repack_doc.insert()
    repack_doc.submit()
