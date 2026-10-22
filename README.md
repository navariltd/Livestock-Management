# Livestock Management

An integrated livestock management solution built for ERPNext, designed to bridge the gap between daily farm operations and financial accounting. This application enables poultry farms to manage routine operational activities while ensuring compliance with International Accounting Standard 41 (IAS 41) - Agriculture by linking farm activities directly to the valuation of biological assets.

## Key Features

- **IAS 41 Compliance**: Automates the capitalization of qualifying routine costs (feeds, vaccines, medication) directly into the value of biological assets to ensure accurate profitability tracking and asset valuation.
- **Integrated Poultry Operations**:
  - **Feeding & Treatment Management**: Automates cost capitalization via "Repack" stock entries when a batch's capitalization status is set to "Active".
  - **Mortality & Culling Tracking**: Dedicated entry types for tracking biological losses with mandatory reason logging.
  - **Egg Collection**: Streamlined recording of egg production (Good, cracked, small, damaged, waste) linked to specific chicken batches.
- **Batch & Flock Identity Enhancement**: Advanced batch management including capitalization start/end dates, capitalization status (Active/Closed), and age calculation based on manufacturing date.
- **Item Enhancements**: Configurable capitalization days and automatic validation for capitalization-related fields.
- **Operational Reporting**: Seamless integration with standard ERPNext modules including Inventory, Manufacturing, Projects, and Accounting.
- **Daily Farm Entry Screen**: A Frappe Desk Page for batch-based feeding, mortality, weighing, produce collection, and observations using shared flock details. It creates draft Stock Entries for standard review and submission, saves Weight Records and Livestock Events immediately, and provides duplicate-save protection and recent activity links while respecting existing permissions and workflows.

- **Feeding Programs**: Feeding Formula records with age ranges, expected intake, expected FCR, and formula-based population of feeding entries.
- **Complete Weight Tracking**: Weight records for animals or batches with sample and population sizes, previous weight, weight gain, and FCR calculations. Scheduled weight-capture tasks also need their generation and completion workflow.
- **Veterinary Workflow**: Veterinary Diagnosis and treatment-plan records covering disease, symptoms, prescriptions, administration details, withdrawal periods, and automatic medical stock issues followed by capitalization where applicable.
- **Livestock Events and Issues**: Reusable husbandry events for non-stock activities, plus issue reporting through ERPNext Helpdesk.
- **Reproduction Management**: Serial-number sex and reproductive status, breeding records, pregnancy diagnosis, expected calving, offspring records, newborn stock receipts, parent and sibling links, and pedigree history.
- **Serial-Number Livestock Support**: End-to-end support for individually identified livestock such as cattle and sheep, alongside batch-based poultry tracking.

## Upcoming Features

The following planned features will reuse standard Frappe and ERPNext capabilities wherever possible:

- **Flock/Batch Performance Dashboard**: Track live population, survival, weight, feed consumption, FCR, and egg yield against age-based targets using standard reports, Number Cards, and Dashboard Charts.
- **Performance Alerts**: Detect unusual mortality, poor growth, and overdue weighing or treatment, with standard Notifications, assignments, and ToDos supporting follow-up.
- **Batch Lifecycle Traceability**: Follow livestock from receipt or birth through husbandry, treatment, transfers, grading, batch splits/merges, and sale using ERPNext stock transactions and linked lifecycle reports.


## Survival Percentage card

The custom Survival Percentage card defaults to the current month through today and the user's default Company. It includes only permitted batches marked **Is Livestock Item**, with Items counted in Nos or Unit. Optional Company, Item, Batch, house, and date filters narrow the scope.

Period survival is `100 × (opening population + animals entering the scope − deaths) / (opening population + animals entering the scope)`. It combines animal counts rather than averaging batch percentages. Sales and explicitly separate Culling-type issues are departures, not deaths. All issues posted under the Mortality type count as deaths; culling recorded under that same type cannot be distinguished automatically. Internal transfers and valuation-only Repacks net out across the selected scope. Transfers into a selected house count as entrants to that house. The card shows **Unavailable** for a missing denominator, stock corrections, incomplete batch transformations, unreadable/unclassified stock issues, or invalid negative balances. Its percentage is an operational period rate, not a lifetime cohort survival estimate. Automatic percentage-change statistics are disabled because they are a different metric.


## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app livestock_management
```

## Veterinary Diagnosis stock transactions

After updating the app, run `bench --site <site-name> migrate` to install the new fields and Stock Entry reference fixture.

1. Configure **Treatment Stock Entry Difference Account** in Livestock Management Settings. Medical issues use this expense ledger; it must belong to the diagnosis company and use its currency.
2. Enter each medicine's **Quantity Consumed** in its Stock UOM and **Source Warehouse**. Dose remains clinical information, not inventory quantity. Select existing medicine batches/serials where the Item requires them.
3. Set **Stock Posting Date** and mark the diagnosis **Completed** before submitting. Submission creates a submitted **Medical / Material Issue** Stock Entry.
4. To increase the livestock valuation, enable **To Capitalize** and select a livestock Batch or Serial No. The capitalisation warehouse defaults to the Batch Location or the serial's current warehouse. Batch costs apply only to available stock in that warehouse; serial-tracked livestock requires an individual Serial No.
5. Optionally allocate submitted Purchase Invoice costs by expense account. Enter amounts in company currency. Only non-stock net expenses are eligible: medicine purchase valuation, taxes, fixed assets and deferred expenses are excluded. Allocations across capitalised diagnoses cannot exceed the eligible invoice expense.

With **To Capitalize** enabled, submission also creates a **Capitalisation / Repack** Stock Entry using the actual issued medicine value plus allocated invoice costs. Both generated entries are linked on the diagnosis, and repeating the submission handler does not create duplicates. If either stock submission fails, the diagnosis and generated entries roll back together. Cancelling the diagnosis cancels the Repack first, then the Medical issue, subject to ERPNext's normal cancellation checks; Purchase Invoices are not cancelled.

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/livestock_management
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

## License

mit
