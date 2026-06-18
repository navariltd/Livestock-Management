import frappe

def on_submit_livestock_entry(doc, method):
    """
    Handle Stock Entry submissions for Feeding and Treatment,
    creating repack entries for active batch capitalisation.
    """
    if doc.purpose == "Material Issue" and doc.stock_entry_type in ["Feeding", "Treatment"]:
        for item in doc.items:
            if item.batch_no:
                batch = frappe.get_doc("Batch", item.batch_no)
                if batch.get("lvm_capitalisation_status") == "Active":
                    create_repack_entry(doc, item)

def create_repack_entry(source_doc, item_row):
    """
    Create and submit a repack Stock Entry for a qualifying feed or treatment batch.
    """
    repack_doc = frappe.new_doc("Stock Entry")
    repack_doc.purpose = "Repack"
    repack_doc.company = source_doc.company

    current_qty = frappe.db.get_value("Batch", item_row.batch_no, "batch_qty") or 1

    expense_account = None

    if source_doc.stock_entry_type == "Feeding":
        expense_account = frappe.get_single_value("Livestock Management Settings", "default_feeding_expense_account") or "Feeding-Expense-Account"
    elif source_doc.stock_entry_type == "Treatment":
        expense_account = frappe.get_single_value("Livestock Management Settings", "default_treatment_expense_account") or "Treatment-Expense-Account"

    repack_doc.append("additional_costs", {
        "description": f"Capitalizing {source_doc.stock_entry_type} for batch {item_row.batch_no}",
        "amount": item_row.amount,
        "expense_account": expense_account
    })

    repack_doc.append("items", {
        "item_code": item_row.item_code,
        "batch_no": item_row.batch_no,
        "s_warehouse": item_row.s_warehouse,
        "t_warehouse": item_row.s_warehouse,
        "qty": current_qty,
        # "is_finished_item": 1
    })

    repack_doc.submit()

def validate_livestock_fields(doc, method):
    if doc.purpose == "Material Issue":
        if doc.stock_entry_type == "Mortality Entry" and not doc.lvm_mortality_reason:
            frappe.throw("Mortality Reason is mandatory for Mortality Entry.")

        if doc.stock_entry_type in ["Feeding", "Treatment"]:
            if not doc.lvm_employee or not doc.lvm_shift_type:
                frappe.throw(f"Employee and Shift Type are mandatory for {doc.stock_entry_type}.")

            if doc.stock_entry_type == "Treatment":
                if not doc.lvm_treatment_type:
                    frappe.throw("Treatment Type is mandatory for Treatment entries.")

    validate_egg_collection(doc)

def validate_egg_collection(doc):
    if doc.purpose == "Material Receipt" and doc.lvm_is_egg_collection:
        if not doc.lvm_collector_name:
            frappe.throw("Collector Name is mandatory for Egg Collection.")
        for item in doc.items:
            if not item.batch_no:
                frappe.throw(f"Batch ID is mandatory for item {item.item_code} in Egg Collection.")
