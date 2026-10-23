# Survival Percentage card

The custom Survival Percentage card defaults to the current month through today and the user's default Company. It includes only permitted batches marked **Is Livestock Item**, with Items counted in Nos or Unit. Optional Company, Item, Batch, house, and date filters narrow the scope.

Period survival is `100 × (opening population + animals entering the scope − deaths) / (opening population + animals entering the scope)`. It combines animal counts rather than averaging batch percentages. Sales and explicitly separate Culling-type issues are departures, not deaths. All issues posted under the Mortality type count as deaths; culling recorded under that same type cannot be distinguished automatically. Internal transfers and valuation-only Repacks net out across the selected scope. Transfers into a selected house count as entrants to that house. The card shows **Unavailable** for a missing denominator, stock corrections, incomplete batch transformations, unreadable/unclassified stock issues, or invalid negative balances. Its percentage is an operational period rate, not a lifetime cohort survival estimate. Automatic percentage-change statistics are disabled because they are a different metric.

See also the [performance targets guide](performance_targets.md) and [documentation index](README.md).
