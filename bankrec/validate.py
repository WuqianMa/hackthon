from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv
import re

from .io import FIELDS, EXCEPTIONS, cents, rows

MAX_BYTES = 60 * 1024 * 1024
MAX_ROWS = 3_000_000


def validate(path, transactions, catalog):
    """Strict writer contract, plus catalog membership and coverage absent from scorer checks."""
    path = Path(path)
    errors, seen, covered, types = [], set(), set(), {}
    n = 0
    def err(line, message):
        if len(errors) < 100:
            errors.append({"row": line, "message": message})
    if path.stat().st_size > MAX_BYTES:
        err(None, "uncompressed CSV exceeds 60 MiB")
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        if next(reader, None) != FIELDS:
            err(1, "header must exactly equal the five canonical fields in order")
        for lineno, r in enumerate(reader, 2):
            n += 1
            if len(r) != 5:
                err(lineno, "expected five fields")
                continue
            tid, iid, amount, cat, exc = r
            if tid not in transactions:
                err(lineno, "unknown or cross-phase bank ID")
            covered.add(tid)
            key = (tid, iid)
            if key in seen:
                err(lineno, "duplicate bank/item pair")
            seen.add(key)
            kind = "item" if iid else "category"
            if tid in types and types[tid] != kind:
                err(lineno, "mixed item and category rows")
            types[tid] = kind
            if exc and exc not in EXCEPTIONS:
                err(lineno, "unknown exception")
            if iid:
                item = catalog.item(iid)
                if not item:
                    err(lineno, "unknown item ID (syntax alone is insufficient)")
                elif tid in transactions and item["issue"] > transactions[tid]["booking_date"]:
                    err(lineno, "item issued after bank booking date")
                if cat:
                    err(lineno, "item row has category")
                if not re.fullmatch(r"\d+\.\d{2}", amount):
                    err(lineno, "amount must have two decimals and be non-negative")
                else:
                    a = Decimal(amount)
                    if not a.is_finite() or a > Decimal("1e12"):
                        err(lineno, "amount out of range")
                    elif item and cents(amount) > item["total"] and exc != "DUPLICATE_PAYMENT":
                        err(lineno, "allocation exceeds document total")
            else:
                if amount:
                    err(lineno, "no-item row has amount")
                if cat not in catalog.categories:
                    err(lineno, "missing or unknown category")
                if cat == "UNIDENTIFIED" and exc != "UNIDENTIFIED":
                    err(lineno, "unidentified fallback must carry its exception")
    if n > MAX_ROWS:
        err(None, "exceeds 3,000,000 rows")
    missing = set(transactions) - covered
    if missing:
        err(None, f"{len(missing)} bank lines omitted")
    # Replay in bank chronology to catch accidental over-clearing; returns re-open balances.
    balances = {}
    warnings = []
    for lineno, r in enumerate(rows(path), 2):
        iid = r["item_id"]
        if not iid or not re.fullmatch(r"\d+\.\d{2}", r["amount"]):
            continue
        item = catalog.item(iid)
        if not item:
            continue
        bal = balances.setdefault(iid, item["initial"])
        amt, exc = cents(r["amount"]), r["exception"]
        if exc == "RETURNED":
            if bal + amt > item["total"]:
                if len(warnings) < 50:
                    warnings.append({"row": lineno, "message": "return predates observable clearing history; balance capped at total"})
            balances[iid] = min(item["total"], bal + amt)
        elif exc != "DUPLICATE_PAYMENT":
            if amt > bal:
                err(lineno, "aggregate allocation exceeds remaining balance")
            balances[iid] = max(0, bal - amt)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "rows": n,
            "bank_lines": len(transactions), "covered": len(covered & transactions.keys()),
            "uncompressed_bytes": path.stat().st_size, "max_bytes": MAX_BYTES}
