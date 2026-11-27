# Reliability

## SLOs / targets
_TBD_

## Failure modes & mitigations
| Failure | Detection | Mitigation |
|---------|-----------|------------|
| Malformed or hostile CSV upload | Loader returns row-numbered `RowError`s | File is not applied; nothing is guessed; size caps bound time and memory |
| Absurd or non-finite number from a model or caller | `ValueError` / `TypeError` from the domain core | Caps on values and durations; QA maths uses a fixed 60-digit Decimal context; raw `decimal` errors are mapped to `ValueError` |
| Guard input missing (approval totals, after-media check, severity, recorded swaps) | `GuardFailed` / `ValueError`, or the line is flagged | Guards fail closed; the caller must supply the facts explicitly |
| Alert noise | Dedup by key in `calc/alerts.filter_new` | Slip/overspend re-sent only when worse; blocked once per episode |

## Runbooks
_TBD_
