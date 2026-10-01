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

- **Feeding Programs**: Feeding Formula records with age ranges, expected intake, expected FCR, and formula-based population of feeding entries.
- **Complete Weight Tracking**: Weight records for animals or batches with sample and population sizes, previous weight, weight gain, and FCR calculations. Scheduled weight-capture tasks also need their generation and completion workflow.
- **Veterinary Workflow**: Veterinary Diagnosis and treatment-plan records covering disease, symptoms, prescriptions, administration details, withdrawal periods, and automatic medical stock issues followed by capitalization where applicable.
- **Livestock Events and Issues**: Reusable husbandry events for non-stock activities, plus issue reporting through ERPNext Helpdesk.
- **Reproduction Management**: Serial-number sex and reproductive status, breeding records, pregnancy diagnosis, expected calving, offspring records, newborn stock receipts, parent and sibling links, and pedigree history.
- **Serial-Number Livestock Support**: End-to-end support for individually identified livestock such as cattle and sheep, alongside batch-based poultry tracking.

## Upcoming Features

The following capabilities are defined in the product proposal but are not yet fully implemented:

- **Capitalization and Valuation Automation**: Automatic closure of batch capitalization when the end date is reached, ongoing age-in-days updates, scheduled background updates, fair-value adjustment through stock reconciliation, and reproduction accounting configuration.

## Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app livestock_management
```

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
