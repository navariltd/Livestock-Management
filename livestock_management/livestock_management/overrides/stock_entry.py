import frappe

def on_submit_feeding(doc, method):
    """
    Handle feed submission and create repack entries for active batch capitalisation.

    This function is triggered when a Stock Entry document is submitted. It processes
    feeding material issues and creates corresponding repack entries for batches that
    have an active capitalisation status.

    Args:
        doc (frappe.Document): The Stock Entry document being submitted.
        method (str): The hook method name (typically 'on_submit').
    """
    if doc.purpose == "Material Issue" and doc.lvm_material_issue_purpose == "Feeding":

        for item in doc.items:
            if item.batch_no:
                batch = frappe.get_doc("Batch", item.batch_no)

                if batch.get("lvm_capitalisation_status") == "Active":
                    create_repack_entry(doc, item)

def create_repack_entry(feeding_doc, item_row):
    """
    Create and submit a repack Stock Entry for a qualifying feed batch.

    This builds a Stock Entry of type Repack for the same company as the
    feeding document, copies the batch and warehouse information from the
    source row, and records the feed amount as an additional cost.
    """
    repack_doc = frappe.new_doc("Stock Entry")
    repack_doc.stock_entry_type = "Repack"
    repack_doc.purpose = "Material Transfer for Manufacture"
    repack_doc.company = feeding_doc.company

    repack_doc.append("additional_costs", {
        "description": f"Capitalizing feed for batch {item_row.batch_no}",
        "amount": item_row.amount
    })

    repack_doc.append("items", {
        "item_code": item_row.item_code,
        "batch_no": item_row.batch_no,
        "s_warehouse": item_row.s_warehouse,
        "t_warehouse": item_row.s_warehouse,
        "qty": 0
    })

    repack_doc.insert()
    repack_doc.submit()


def validate_livestock_fields(doc, method):
    if doc.purpose == "Material Issue":

        if doc.lvm_material_issue_purpose == "Mortality Entry":
            if not doc.lvm_mortality_reason:
                frappe.throw("Mortality Reason is mandatory when Material Issue Purpose is 'Mortality Entry'.")

        if doc.lvm_material_issue_purpose in ["Feeding", "Treatment"]:
            if not doc.lvm_employee or not doc.lvm_shift_type:
                frappe.throw(f"Employee and Shift Type are mandatory for {doc.lvm_material_issue_purpose}.")

    validate_egg_collection(doc)

def validate_egg_collection(doc):
    if doc.purpose == "Material Receipt" and doc.lvm_is_egg_collection:
        if not doc.lvm_collector_name:
            frappe.throw("Collector Name is mandatory for Egg Collection.")

        for item in doc.items:
            if not item.batch_no:
                frappe.throw(f"Batch ID is mandatory for item {item.item_code} in Egg Collection.")
