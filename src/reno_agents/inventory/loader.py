"""CSV loaders that accept what Excel / Google Sheets save, and refuse to guess at anything else.

Uploads come from admins but are treated as untrusted: sizes are capped, every row error carries
the line the row starts on, and a parse failure becomes an error instead of an exception.
"""

import csv
import io
from collections import Counter
from typing import TypeVar

from pydantic import ValidationError

from reno_agents.calc.money import SYMBOL_CURRENCIES, parse_money_with_symbol
from reno_agents.inventory.schema import InventoryItem, LaborRate, LoadResult, RowError, _Row

M = TypeVar("M", bound=_Row)

MAX_COLUMNS = 200
MAX_ROWS = 20_000
MAX_ERRORS = 500


def load_inventory(text: str, *, currency: str) -> LoadResult[InventoryItem]:
    """Parse ``inventory.csv`` text. Every row error is reported with its line number."""
    return _load(text, InventoryItem, key_field="sku", currency=currency)


def load_labor_rates(text: str, *, currency: str) -> LoadResult[LaborRate]:
    """Parse ``labor_rates.csv`` text."""
    return _load(text, LaborRate, key_field="task_code", currency=currency)


def _header_errors(header: list[str], columns: list[str]) -> list[str]:
    problems = []
    if len(header) > MAX_COLUMNS:
        return [f"too many columns ({len(header)}); at most {MAX_COLUMNS} are allowed"]
    missing = [c for c in columns if c not in header]
    if missing:
        problems.append(f"missing columns: {', '.join(missing)}")
    duplicated = sorted(name for name, n in Counter(header).items() if name and n > 1)
    if duplicated:
        problems.append(f"duplicate columns: {', '.join(duplicated)}")
    return problems


def _symbol_error(raw: str, expected_currency: str) -> str | None:
    try:
        _, symbol = parse_money_with_symbol(raw)
    except ValueError:
        return None  # the model reports the bad number itself
    if symbol is not None and expected_currency not in SYMBOL_CURRENCIES[symbol]:
        return f"currency symbol {symbol} does not match currency {expected_currency}"
    return None


def _load(text: str, model: type[M], *, key_field: str, currency: str) -> LoadResult[M]:
    columns = list(model.model_fields)
    reader = csv.reader(io.StringIO(text.removeprefix("﻿"), newline=""))
    items: list[M] = []
    errors: list[RowError] = []

    try:
        header_row = next(reader, None)
    except csv.Error as exc:
        return LoadResult(items, [RowError(1, None, f"could not read the header: {exc}")])
    if header_row is None:
        return LoadResult(items, [RowError(1, None, "file is empty")])
    header = [name.strip().lower() for name in header_row]
    problems = _header_errors(header, columns)
    if problems:
        return LoadResult(items, [RowError(1, None, "; ".join(problems))])
    index = {name: header.index(name) for name in columns}

    expected_currency = currency.strip().upper()
    seen_keys: set[str] = set()
    rows_read = 0
    while True:
        line = reader.line_num + 1  # the line this row starts on
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            errors.append(RowError(line, None, f"could not read this row: {exc}"))
            break
        if not any(cell.strip() for cell in cells):
            continue
        rows_read += 1
        if rows_read > MAX_ROWS:
            errors.append(RowError(line, None, f"too many rows; at most {MAX_ROWS} are allowed"))
            break
        if len(errors) >= MAX_ERRORS:
            errors.append(RowError(line, None, f"stopped after {MAX_ERRORS} errors"))
            break
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

        for money_field in model.MONEY_FIELDS:
            problem = _symbol_error(raw[money_field], expected_currency)
            if problem:
                row_errors.append(RowError(line, money_field, problem))

        row_currency = raw["currency"].strip().upper()
        if row_currency and row_currency != expected_currency:
            row_errors.append(
                RowError(line, "currency", f"expected {expected_currency}, got {row_currency}")
            )

        key = raw[key_field].strip().casefold()
        if key and key in seen_keys:
            row_errors.append(
                RowError(line, key_field, f"duplicate {key_field} {raw[key_field]!r}")
            )

        if row_errors:
            errors.extend(row_errors)
        elif item is not None:
            seen_keys.add(key)  # only accepted rows claim their key
            items.append(item)
    return LoadResult(items, errors)
