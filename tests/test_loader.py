from pathlib import Path

from reconciler.loader import load_bank, load_ledger

DATA = Path(__file__).resolve().parent.parent / "data"


def test_load_ledger_parses_dates_and_amounts():
    entries = load_ledger(DATA / "sample_ledger.csv")
    assert len(entries) == 21
    first = entries[0]
    assert first.ledger_id == "L01"
    assert first.date.isoformat() == "2026-07-01"
    assert first.amount == -54.99
    assert first.category == "Software"


def test_load_bank_parses_dates_and_amounts():
    txns = load_bank(DATA / "sample_bank_export.csv")
    assert len(txns) == 23
    interest = txns[-1]
    assert interest.bank_id == "B23"
    assert interest.amount == 1.42
