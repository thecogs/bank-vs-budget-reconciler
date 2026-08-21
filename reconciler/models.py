"""Data structures shared across the reconciler."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class LedgerEntry:
    ledger_id: str
    date: date
    description: str
    amount: float
    category: str = ""


@dataclass
class BankTransaction:
    bank_id: str
    date: date
    description: str
    amount: float


@dataclass
class ReconciliationResult:
    """One row of the reconciliation output.

    `flag` is one of: matched, amount_mismatch, missing_in_ledger,
    missing_in_bank, possible_duplicate_charge.
    """

    flag: str
    severity: str  # info | ok | warning | error
    ledger_entry: Optional[LedgerEntry]
    bank_transaction: Optional[BankTransaction]
    detail: str
    explanation: Optional[str] = field(default=None)

    @property
    def amount(self) -> float:
        if self.bank_transaction is not None:
            return self.bank_transaction.amount
        if self.ledger_entry is not None:
            return self.ledger_entry.amount
        return 0.0

    @property
    def date_str(self) -> str:
        d = self.bank_transaction.date if self.bank_transaction else (
            self.ledger_entry.date if self.ledger_entry else None
        )
        return d.isoformat() if d else "-"

    @property
    def description(self) -> str:
        if self.bank_transaction and self.ledger_entry:
            return f"{self.ledger_entry.description} / {self.bank_transaction.description}"
        if self.bank_transaction:
            return self.bank_transaction.description
        if self.ledger_entry:
            return self.ledger_entry.description
        return ""
