"""These tests run against the sample data in data/ and pin down the
exact discrepancies that are planted there on purpose. If you change
the sample CSVs, update these expectations too.
"""

from pathlib import Path

import pytest

from reconciler.loader import load_bank, load_ledger
from reconciler.matcher import reconcile

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def results():
    ledger = load_ledger(DATA / "sample_ledger.csv")
    bank = load_bank(DATA / "sample_bank_export.csv")
    return reconcile(ledger, bank)


def by_flag(results, flag):
    return [r for r in results if r.flag == flag]


def test_every_row_is_accounted_for(results):
    ledger = load_ledger(DATA / "sample_ledger.csv")
    bank = load_bank(DATA / "sample_bank_export.csv")
    ledger_rows_seen = sum(1 for r in results if r.ledger_entry is not None)
    bank_rows_seen = sum(1 for r in results if r.bank_transaction is not None)
    assert ledger_rows_seen == len(ledger)
    assert bank_rows_seen == len(bank)


def test_clean_matches_found(results):
    matched = by_flag(results, "matched")
    # 18 clean 1:1 matches, plus the one side of the duplicate-charge
    # pair (L04) that does match correctly
    assert len(matched) == 19


def test_timing_lag_still_matches(results):
    matched = by_flag(results, "matched")
    whitfield = next(r for r in matched if "Whitfield" in r.description)
    assert whitfield.ledger_entry.date.isoformat() == "2026-07-02"
    assert whitfield.bank_transaction.date.isoformat() == "2026-07-06"
    assert "4 days after" in whitfield.detail


def test_duplicate_charge_detected(results):
    dupes = by_flag(results, "possible_duplicate_charge")
    assert len(dupes) == 1
    assert dupes[0].bank_transaction.bank_id == "B04"
    assert dupes[0].bank_transaction.amount == -6.75


def test_amount_mismatch_detected(results):
    mismatches = by_flag(results, "amount_mismatch")
    assert len(mismatches) == 1
    m = mismatches[0]
    assert m.ledger_entry.ledger_id == "L08"
    assert m.bank_transaction.bank_id == "B09"
    assert m.amount == -94.32
    assert "10.32" in m.detail


def test_missing_in_ledger_detected(results):
    missing = by_flag(results, "missing_in_ledger")
    bank_ids = {r.bank_transaction.bank_id for r in missing}
    # the monthly service fee and the interest payment were never logged
    assert "B07" in bank_ids
    assert "B23" in bank_ids
    interest = next(r for r in missing if r.bank_transaction.bank_id == "B23")
    assert interest.severity == "info"  # $1.42, immaterial
    fee = next(r for r in missing if r.bank_transaction.bank_id == "B07")
    assert fee.severity == "warning"


def test_missing_in_bank_detected(results):
    outstanding = by_flag(results, "missing_in_bank")
    assert len(outstanding) == 1
    assert outstanding[0].ledger_entry.ledger_id == "L02"


def test_no_double_counting_of_flagged_rows(results):
    total_flagged = len(results) - len(by_flag(results, "matched"))
    # 1 duplicate + 1 mismatch + 2 missing-in-ledger + 1 missing-in-bank
    assert total_flagged == 5
