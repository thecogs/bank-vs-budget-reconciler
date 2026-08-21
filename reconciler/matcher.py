"""The matching engine.

No AI here on purpose: whether two rows refer to the same real-world
transaction is a deterministic question, and a reconciliation tool
that gave a different answer on every run would be worse than the
spreadsheet it replaces. The LLM's job (see explainer.py) is limited
to explaining what the matcher already decided.

Two passes:

  Pass A - exact amount, close date.  Handles clean matches, timing
           lag (ACH/checks clearing days after they're logged), and
           surfaces duplicate charges as a side effect (when two bank
           rows both fit one ledger row, only the better one is used).

  Pass B - close date, similar description, but the amount differs.
           Handles typos and partial-amount discrepancies without
           silently treating them as unrelated transactions.

Anything left over after both passes is either sitting only in the
bank feed (missing_in_ledger) or only in the ledger (missing_in_bank).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from rapidfuzz import fuzz

from reconciler.models import BankTransaction, LedgerEntry, ReconciliationResult

AMOUNT_EXACT_TOLERANCE = 0.01
DATE_TOLERANCE_DAYS = 7
MISMATCH_MAX_RELATIVE_DIFF = 0.6  # ignore candidates wildly different in size
MISMATCH_DESC_MIN_SIMILARITY = 45  # rapidfuzz 0-100 scale
DUPLICATE_DESC_MIN_SIMILARITY = 80
DUPLICATE_DATE_WINDOW_DAYS = 3
IMMATERIAL_AMOUNT = 5.00


@dataclass
class _Candidate:
    ledger_idx: int
    bank_idx: int
    score: float
    date_diff: int


def _date_score(diff_days: int, tolerance: int = DATE_TOLERANCE_DAYS) -> float:
    if diff_days > tolerance:
        return 0.0
    return 1.0 - (diff_days / tolerance)


def _desc_similarity(a: str, b: str) -> float:
    """0-100 fuzzy match, robust to reordering and punctuation noise."""
    return fuzz.token_sort_ratio(a.upper(), b.upper())


def reconcile(
    ledger: List[LedgerEntry], bank: List[BankTransaction]
) -> List[ReconciliationResult]:
    unmatched_ledger = set(range(len(ledger)))
    unmatched_bank = set(range(len(bank)))
    results: List[ReconciliationResult] = []

    # ---- Pass A: exact amount, date within tolerance ----
    candidates: List[_Candidate] = []
    for li in unmatched_ledger:
        for bi in unmatched_bank:
            if abs(ledger[li].amount - bank[bi].amount) > AMOUNT_EXACT_TOLERANCE:
                continue
            diff = abs((bank[bi].date - ledger[li].date).days)
            dscore = _date_score(diff)
            if dscore <= 0:
                continue
            sim = _desc_similarity(ledger[li].description, bank[bi].description) / 100
            score = 0.55 * dscore + 0.45 * sim
            candidates.append(_Candidate(li, bi, score, diff))

    candidates.sort(key=lambda c: c.score, reverse=True)
    matched_bank_desc: dict[int, str] = {}
    for c in candidates:
        if c.ledger_idx not in unmatched_ledger or c.bank_idx not in unmatched_bank:
            continue
        ledger_entry = ledger[c.ledger_idx]
        bank_txn = bank[c.bank_idx]
        detail = "Matched on amount and date."
        if c.date_diff > 2:
            detail = f"Matched — cleared the bank {c.date_diff} days after it was logged."
        results.append(
            ReconciliationResult(
                flag="matched",
                severity="ok",
                ledger_entry=ledger_entry,
                bank_transaction=bank_txn,
                detail=detail,
            )
        )
        unmatched_ledger.discard(c.ledger_idx)
        unmatched_bank.discard(c.bank_idx)
        matched_bank_desc[c.bank_idx] = bank_txn.description

    # ---- Pass B: same-ish date and description, amount differs ----
    mismatch_candidates: List[_Candidate] = []
    for li in unmatched_ledger:
        for bi in unmatched_bank:
            le, bt = ledger[li], bank[bi]
            if le.amount == 0 or bt.amount == 0:
                continue
            # only compare like-signed amounts (an expense shouldn't "mismatch" a deposit)
            if (le.amount < 0) != (bt.amount < 0):
                continue
            rel_diff = abs(le.amount - bt.amount) / max(abs(le.amount), abs(bt.amount))
            if rel_diff > MISMATCH_MAX_RELATIVE_DIFF:
                continue
            diff = abs((bt.date - le.date).days)
            dscore = _date_score(diff)
            if dscore <= 0:
                continue
            sim = _desc_similarity(le.description, bt.description)
            if sim < MISMATCH_DESC_MIN_SIMILARITY:
                continue
            score = 0.5 * dscore + 0.5 * (sim / 100)
            mismatch_candidates.append(_Candidate(li, bi, score, diff))

    mismatch_candidates.sort(key=lambda c: c.score, reverse=True)
    for c in mismatch_candidates:
        if c.ledger_idx not in unmatched_ledger or c.bank_idx not in unmatched_bank:
            continue
        le, bt = ledger[c.ledger_idx], bank[c.bank_idx]
        delta = round(bt.amount - le.amount, 2)
        results.append(
            ReconciliationResult(
                flag="amount_mismatch",
                severity="error" if abs(delta) > 25 or abs(delta) / max(abs(le.amount), 0.01) > 0.10 else "warning",
                ledger_entry=le,
                bank_transaction=bt,
                detail=f"Ledger says {le.amount:.2f}, bank cleared {bt.amount:.2f} "
                f"(difference of {delta:+.2f}).",
            )
        )
        unmatched_ledger.discard(c.ledger_idx)
        unmatched_bank.discard(c.bank_idx)

    # ---- Leftover bank transactions: duplicate charge, or missing in ledger ----
    for bi in sorted(unmatched_bank):
        bt = bank[bi]
        dup_of: Optional[str] = None
        for other_bi, other_desc in matched_bank_desc.items():
            other = bank[other_bi]
            if abs(other.amount - bt.amount) > AMOUNT_EXACT_TOLERANCE:
                continue
            if abs((other.date - bt.date).days) > DUPLICATE_DATE_WINDOW_DAYS:
                continue
            if _desc_similarity(other_desc, bt.description) < DUPLICATE_DESC_MIN_SIMILARITY:
                continue
            dup_of = other.bank_id
            break
        if dup_of:
            results.append(
                ReconciliationResult(
                    flag="possible_duplicate_charge",
                    severity="error",
                    ledger_entry=None,
                    bank_transaction=bt,
                    detail=f"Looks like a second charge for the same thing as {dup_of} "
                    f"— same amount, same description, {bt.date.isoformat()}.",
                )
            )
        else:
            severity = "info" if abs(bt.amount) < IMMATERIAL_AMOUNT else "warning"
            results.append(
                ReconciliationResult(
                    flag="missing_in_ledger",
                    severity=severity,
                    ledger_entry=None,
                    bank_transaction=bt,
                    detail="This cleared the bank but there's no matching entry in the ledger.",
                )
            )

    # ---- Leftover ledger entries: nothing in the bank feed yet ----
    for li in sorted(unmatched_ledger):
        le = ledger[li]
        results.append(
            ReconciliationResult(
                flag="missing_in_bank",
                severity="warning",
                ledger_entry=le,
                bank_transaction=None,
                detail="Logged in the ledger but hasn't shown up in the bank feed "
                "— outstanding, or entered in error.",
            )
        )

    results.sort(key=lambda r: r.date_str)
    return results
