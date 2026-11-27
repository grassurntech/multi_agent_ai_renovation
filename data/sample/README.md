# Sample data

Starter inventory and labor rates so the project runs out of the box.

**Everything here is fictional.** Brands (Northfield, Harbor Coat, Kelvo, Securo, Brindlewood,
Corvane, Fenwyck, Glimmerline, Hollowpine, Larkmere, Quillon), suppliers (Acme Supply,
BuildRight Co, ApplianceHub), models, specs and prices are made up for demonstration. Any
resemblance to a real company or product is accidental. Replace these files with your own approved
inventory before real use, and never commit real vendor pricing to a public fork.

| File | Rows | Notes |
|------|------|-------|
| `inventory.csv` | 60 | 19 substitution groups, each with at least 3 active approved items (good / better / best). One item is expired (`PNT-004`) and one is not approved (`FLR-004`) so the filters can be seen working. |
| `labor_rates.csv` | 19 | One rate per task type, covering every trade step from `demo` to `clean`. `rate` is per `unit` of work; `typical_hours_per_unit` is used only for durations. |

Column definitions are in the [system design](../../docs/design-docs/reno-agents-system.md#6-inventory-and-labor-data).
