# Age-based performance targets

Create a **Livestock Performance Profile** from Desk search as Stock Manager or System Manager. Enter a descriptive profile name, then add one target row per biological age day or use standard Frappe Data Import with child rows. Age zero is the hatch/birth date. Export a template first to obtain the correct parent and child column names.

| Target            | Unit                            |
| ----------------- | ------------------------------- |
| Average weight    | kg per animal                   |
| Daily feed intake | g per animal per day            |
| Interval FCR      | kg feed per kg live-weight gain |
| Hen-day egg yield | percentage                      |

Leave an individual target blank when unspecified. Enter `0` for an explicit zero. Target cells are numeric text fields with server validation so Frappe does not convert missing targets to zero. Negative, non-finite, and non-numeric targets are rejected. Ages must be unique non-negative whole days; egg yield cannot exceed 100%.

For an all-female laying flock, enable **All-Female Laying Flock** and select all egg Items laid, including cracked and damaged eggs. These must be stock Items counted in Nos or Unit. Do not select non-egg produce. Hen-day yield is unavailable for mixed-sex flocks or profiles not declared as laying flocks.

Submit the profile. On each Batch, select its **Performance Profile** and enter the verified **Hatch/Birth Date**. Manufacturing date is not used as a fallback. Existing batches are not assigned automatically. Stock Users can read profiles; Stock Managers and System Managers can create, import, submit, cancel, and amend them. To revise targets, amend or create a new submitted profile and reassign the Batch. The current assignment determines historical comparisons; Batch version history records assignment changes.

Open **Livestock Batch Performance report** and select Company, Livestock Item, dates, and optionally Batch and House. Population-based targets require stock UOM Nos or Unit.

- Weight targets use the age on the latest valid weight measurement, not the report end date. Weight Records need explicit Company, House, Kg UOM, positive average weight and valid sample size. Choose a House when a batch occupies multiple houses; a single-house sample does not represent a multi-house batch.
- Period feed target is the sum of daily closing population × the matching age's intake in grams ÷ 1,000. Actual feed uses submitted Feeding Material Issues and stock quantities converted to kg.
- FCR uses the same shared measured-interval calculation as the Number Card: feed between two weights divided by live-weight gain, with no population-changing movements between the measurements. Both measurements must be within the report period. The target is selected at the ending measurement's age. For multiple houses, actual and target FCR are weighted by biomass gain; the data notes list each house's interval and date columns show their overall bounds.
- Hen-day yield is 100 × configured egg count ÷ the sum of daily closing hen populations. The target is the population-weighted average of daily yield targets. Submitted produce receipts use stock quantity, so trays or cartons already converted to Nos/Unit are not converted again. Non-egg Items are excluded from egg yield but remain part of generic produce totals.

Variance is actual minus target. Percentage variance is unavailable when the target is zero. Egg-yield variance is in percentage points. There is no automatic good/bad colouring.

Daily targets are exact matches with no interpolation. A missing target on any day with positive population leaves the corresponding period target blank. Missing dates, inaccessible records, unknown units or houses, invalid population exposure, and unsupported FCR intervals produce blank comparisons with a note instead of a partial total. An actual value of zero means no matching readable operations were recorded; it does not prove an unrecorded operation never occurred.

## Deployment and checks

Run `bench --site YOUR_SITE migrate`, then `bench --site YOUR_SITE clear-cache` and reload Desk. This installs three DocTypes and the two Batch fields. New charts, alerts and cards are outside this release.

For a manual check, a stable flock of 100 animals over two days with targets of 100 g/day needs 20 kg feed. If 22 kg is recorded, variance is +2 kg (+10%). A weight of 1.3 kg against its measurement-age target of 1.2 kg gives +0.1 kg (+8.33%). With 160 eggs, hen-day yield is 80%; an 80% target gives zero percentage-point variance. Use valid measured intervals and feed to check FCR separately; mortality within an interval makes the simple FCR unavailable.
