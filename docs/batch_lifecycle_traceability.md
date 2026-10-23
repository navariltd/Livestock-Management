# Batch lifecycle traceability

Open **Batch Lifecycle Traceability** from the Livestock workspace's Reports group, its sidebar, or the **Lifecycle Traceability** button on a saved Batch. Select Company, Batch, and To Date. From Date, Warehouse, and Event Type are optional; **Include Related Batches** defaults on.

This is a read-only Script Report. It does not create transactions, repair historical records, or add lineage fields. Normal ERPNext stock documents and existing livestock records remain the source of truth.

## Events and quantities

| Event                               | Source                                                                                  |
| ----------------------------------- | --------------------------------------------------------------------------------------- |
| Receipt / supplier return           | Submitted Purchase Receipts, stock-updating Purchase Invoices and other posted receipts |
| Birth                               | Material Receipts linked to a readable submitted Offspring Record                       |
| Transfer                            | Material Transfers; departures and arrivals appear separately by warehouse              |
| Split / merge / replacement         | Complete, count-balanced Repack allocations                                             |
| Reclassification / possible grading | Eligible Repack relationships between different Items; grading intent cannot be proven  |
| Capitalisation                      | Capitalisation Repacks, without creating parent/child relationships                     |
| Mortality / culling                 | Submitted stock issues using the corresponding entry type                               |
| Sale / customer return              | Delivery Notes and stock-updating Sales Invoices; non-stock billing is excluded         |
| Correction                          | Stock Reconciliation                                                                    |
| Feeding / produce collection        | Submitted header-linked Stock Entries                                                   |
| Treatment                           | Submitted completed Veterinary Diagnoses and submitted linked medicine issues           |
| Husbandry                           | Completed Livestock Events, using Starts On                                             |
| Weighing                            | Saved, non-cancelled Weight Records, using measurement time                             |

Animal quantities come from stock ledger batch allocations, including legacy batch numbers and Serial and Batch Bundles. A bundle replaces the legacy field; the report never adds both. Allocations are grouped once per document, batch, and warehouse. Incoming and outgoing values remain separate, so same-batch Repacks can show both without representing new animals.

Feed, medicine, produce, weights, and husbandry are linked activities with **blank animal quantities**. The Activity Warehouse column identifies their explicit historical location. Treatment documents and capitalisation entries retain their own rows and readable references to the common diagnosis or stock issue. Summing incoming quantities alone does not calculate a current population: transfers and Repacks can have both sides.

## Related batches and evidence

Related history is inferred from readable submitted Repack records whose entire stock allocation agrees with the accessible stock ledger. The report requires positive whole-animal quantities in compatible count UOMs, complete batch allocations, and balanced inputs and outputs. Non-livestock, inaccessible, incomplete, or unbalanced allocations prevent inference.

One-to-many splits, many-to-one merges, and one-to-one replacements create relationships labelled **Inferred from Repack**. Unchanged batch quantities and cost capitalisation create no relationships. A partial split can retain some stock under the original batch. An unchanged allocation alongside a transformation is excluded from the relationship.

Many-to-many or otherwise ambiguous Repacks appear as **Ambiguous transformation**, with only readable associated batches listed; they do not expand the lineage. This report cannot establish individual-animal ancestry or resolve ambiguous legacy transactions.

Expansion follows valid relationships in both directions, including connected co-parent and sibling branches. Parent, child, and related batch names link to their Batch forms. Traversal is cycle-safe and limited to 200 batches and 20 relationship levels; exceeding either limit raises an error instead of returning an apparently complete partial history. Disable Include Related Batches to inspect one batch.

Relationship discovery covers all history up to To Date. From Date, Warehouse, and Event Type apply afterward to displayed events, so they do not hide an ancestor needed to reach a related batch. To Date remains the historical cutoff for both discovery and events.

## Permissions and historical limitations

Stock Users, Stock Managers, and System Managers can access the report, subject to standard document permissions. Stock Ledger Entry read permission is required. Company, Batch, Item, Warehouse, source document, and Customer access are respected. Optional sources that cannot be read are omitted with a report-level notice. Child allocations are read only through accessible parents; hidden related batches and customer names are not exposed.

Eligible Items are batch-tracked stock Items counted in Nos or Unit. Historical batches do not need the Is Livestock Item checkbox. This eligibility rule cannot establish that an otherwise qualifying Item is biologically livestock; select the appropriate root batch.

Operational activities need an explicit Company and an accessible historical warehouse. A diagnosis may use its explicit capitalisation warehouse or its readable linked medicine issue's explicit house. The current Batch location is never used to guess historical locations. Legacy activities without sufficient scope are omitted and the report explains this limitation. Missing origin links leave a receipt classified as Receipt rather than Birth.

The report is a permission-dependent view, not proof of a complete chain of custody. Historical transactions with missing links or stock posted outside ERPNext cannot be reconstructed automatically. Customer links show permitted parties; revenue, non-stock invoices, planned work, drafts, and cancelled activities are outside this release.

## Deployment and verification

Run `bench --site YOUR_SITE migrate` followed by `bench --site YOUR_SITE clear-cache`, then reload Desk. No business-data migration is needed.

For a manual check, compare a batch's incoming/outgoing rows with its stock ledger. Verify that a receipt of 100 animals shows 100 in, a saved weight changes no animal quantity, and feeding changes no animal quantity. On a split of 100 animals into batches of 60 and 40, both output batches should be related to the source. A same-batch capitalisation Repack should add no descendants. Restrict From Date or Warehouse and confirm that related batches remain discoverable even when the connecting transaction is outside the displayed filter.
