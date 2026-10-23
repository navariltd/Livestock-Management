# Vuna Livestock

An ERPNext app for managing poultry flocks and individually identified livestock. It connects daily farm operations, biological asset valuation, and financial accounting through standard Frappe and ERPNext documents.

## Key Features

- **Daily Farm Operations**: Record feeding, mortality, weighing, egg and other produce collection, and observations through one Desk screen, with existing permissions and approval workflows.
- **Batch and Animal Management**: Track flock identity, age, capitalisation periods, and individually identified livestock using batches and serial numbers.
- **Feeding and Weight Tracking**: Maintain age-based feed formulas, expected intake and FCR, weight samples, population sizes, and recorded weight gains.
- **Veterinary Care and Husbandry**: Manage diagnoses, symptoms, treatment plans, prescriptions, withdrawal periods, husbandry events, and livestock issues.
- **Reproduction Management**: Record breeding, pregnancy checks, expected calving, offspring, newborn stock receipts, and pedigree relationships.
- **Cost Capitalisation**: Add qualifying feed and treatment costs to livestock valuation through Repack entries, supporting biological asset accounting under IAS 41.
- **Performance Dashboard**: Review batch reports, live population, survival, feed consumption, interval FCR, and daily population and mortality trends.
- **Age-Based Performance Targets**: Compare recorded weight, feed, FCR, and hen-day egg yield against submitted daily-age profiles.
- **Batch Lifecycle Traceability**: Follow stock movements and linked activities, with conservative split and merge relationships inferred from Repack entries.

## Upcoming Features

- **Performance Alerts**: Detect unusual mortality, poor growth, and overdue weighing or treatment, using standard Notifications, assignments, and ToDos for follow-up.


## Installation

Requires Frappe, ERPNext, and HRMS. Install the app using the [Bench CLI](https://github.com/frappe/bench):

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench --site YOUR_SITE install-app livestock_management
```

After updating the app, apply schema and fixture changes and clear the site cache:

```bash
bench --site YOUR_SITE migrate
bench --site YOUR_SITE clear-cache
```

## Documentation

See the [feature guides](docs/README.md) for setup steps, calculation rules, permissions, and limitations. Detailed feature documentation is maintained in the `docs/` directory.

## Contributing

Install [pre-commit](https://pre-commit.com/#installation) and enable the repository hooks:

```bash
cd apps/livestock_management
pre-commit install
```

Hooks run Ruff, ESLint, Prettier, and file validation checks. Add feature setup and usage instructions to `docs/` and link them from its documentation index.

## License

[MIT](license.txt)
