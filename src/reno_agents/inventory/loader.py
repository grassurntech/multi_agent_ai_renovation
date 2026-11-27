"""CSV loaders that accept what Excel / Google Sheets save, and refuse to guess at anything else."""

import csv
import io
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from reno_agents.inventory.schema import InventoryItem, LaborRate, LoadResult, RowError

M = TypeVar("M", bound=BaseModel)


def load_inventory(text: str, *, currency: str) -> LoadResult[InventoryItem]:
    """Parse ``inventory.csv`` text. Every row error is reported with its line number."""
    return _load(text, InventoryItem, key_field="sku", currency=currency)


def load_labor_rates(text: str, *, currency: str) -> LoadResult[LaborRate]:
    """Parse ``labor_rates.csv`` text."""
    return _load(text, LaborRate, key_field="task_code", currency=currency)


def _load(text: str, model: type[M], *, key_field: str, currency: str) -> LoadResult[M]:
    columns = list(model.model_fields)
    reader = csv.reader(io.StringIO(text.removeprefix("﻿"), newline=""))
    items: list[M] = []
    errors: list[RowError] = []

    header_row = next(reader, None)
    if header_row is None:
        return LoadResult(items, [RowError(1, None, "file is empty")])
    header = [name.strip().lower() for name in header_row]
    missing = [c for c in columns if c not in header]
    duplicated = sorted({h for h in header if h and header.count(h) > 1})
    if missing or duplicated:
        problems = []
        if missing:
            problems.append(f"missing columns: {', '.join(missing)}")
        if duplicated:
            problems.append(f"duplicate columns: {', '.join(duplicated)}")
        return LoadResult(items, [RowError(1, None, "; ".join(problems))])
    index = {name: header.index(name) for name in columns}

    expected_currency = currency.strip().upper()
    seen_keys: set[str] = set()
    for cells in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in cells):
            continue
        if len(cells) > len(header) and any(c.strip() for c in cells[len(header) :]):
            errors.append(
                RowError(line, None, "row has more values than the header (unquoted comma?)")
            )
            continue
        raw = {name: (cells[i] if i < len(cells) else "") for name, i in index.items()}

        row_errors: list[RowError] = []
        item: M | None = None
        try:
            item = model.model_validate(raw)
        except ValidationError as exc:
            for err in exc.errors():
                field = str(err["loc"][0]) if err["loc"] else None
                row_errors.append(RowError(line, field, err["msg"]))

        row_currency = raw["currency"].strip().upper()
        if row_currency and row_currency != expected_currency:
            row_errors.append(
                RowError(line, "currency", f"expected {expected_currency}, got {row_currency}")
            )

        key = raw[key_field].strip().lower()
        if key and key in seen_keys:
            row_errors.append(
                RowError(line, key_field, f"duplicate {key_field} {raw[key_field]!r}")
            )
        elif key:
            seen_keys.add(key)

        if row_errors:
            errors.extend(row_errors)
        elif item is not None:
            items.append(item)
    return LoadResult(items, errors)
