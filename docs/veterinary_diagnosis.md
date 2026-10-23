# Veterinary Diagnosis stock transactions

1. Configure **Treatment Stock Entry Difference Account** on the Company. Medical issues use this expense ledger; it must belong to the diagnosis company and use its currency.
2. Enter each medicine's **Quantity Consumed** in its Stock UOM and **Source Warehouse**. Dose remains clinical information, not inventory quantity. Select existing medicine batches/serials where the Item requires them.
3. Set **Stock Posting Date** and mark the diagnosis **Completed** before submitting. Submission creates a submitted **Medical / Material Issue** Stock Entry.
4. To increase the livestock valuation, enable **To Capitalize** and select a livestock Batch or Serial No. The capitalisation warehouse defaults to the Batch Location or the serial's current warehouse. Batch costs apply only to available stock in that warehouse; serial-tracked livestock requires an individual Serial No.
5. Optionally allocate submitted Purchase Invoice costs by expense account. Enter amounts in company currency. Only non-stock net expenses are eligible: medicine purchase valuation, taxes, fixed assets and deferred expenses are excluded. Allocations across capitalised diagnoses cannot exceed the eligible invoice expense.

With **To Capitalize** enabled, submission also creates a **Capitalisation / Repack** Stock Entry using the actual issued medicine value plus allocated invoice costs. Both generated entries are linked on the diagnosis, and repeating the submission handler does not create duplicates. If either stock submission fails, the diagnosis and generated entries roll back together. Cancelling the diagnosis cancels the Repack first, then the Medical issue, subject to ERPNext's normal cancellation checks; Purchase Invoices are not cancelled.

See also the [batch lifecycle traceability guide](batch_lifecycle_traceability.md) and [documentation index](README.md).
