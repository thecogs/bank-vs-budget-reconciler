"""CSV loading for ledger and bank export files.

Real bank exports vary a lot (separate debit/credit columns, different
date formats, an extra memo field). Keep this the one place that knows
about that so the matching engine never has to.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import List

from reconciler.models import BankTransaction, LedgerEntry


def _parse_date(raw: str) -> "datetime.date":
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {raw!r}")


def _parse_amount(raw: str) -> float:
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    return round(float(cleaned), 2)


def load_ledger(path: str | Path) -> List[LedgerEntry]:
    entries: List[LedgerEntry] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            entries.append(
                LedgerEntry(
                    ledger_id=row["ledger_id"].strip(),
                    date=_parse_date(row["date"]),
                    description=row["description"].strip(),
                    amount=_parse_amount(row["amount"]),
                    category=(row.get("category") or "").strip(),
                )
            )
    return entries


def load_bank(path: str | Path) -> List[BankTransaction]:
    txns: List[BankTransaction] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            txns.append(
                BankTransaction(
                    bank_id=row["bank_id"].strip(),
                    date=_parse_date(row["date"]),
                    description=row["description"].strip(),
                    amount=_parse_amount(row["amount"]),
                )
            )
    return txns
