"""Bank memos and LLM explanations are untrusted text, so the HTML report
must escape them rather than insert them as markup.
"""

from datetime import date

from reconciler.models import BankTransaction, ReconciliationResult
from reconciler.report import write_html_report

PAYLOAD = '<img src=x onerror="alert(1)">'


def test_report_escapes_untrusted_text(tmp_path):
    result = ReconciliationResult(
        flag="missing_in_ledger",
        severity="error",
        ledger_entry=None,
        bank_transaction=BankTransaction("b1", date(2026, 1, 5), PAYLOAD, -12.5),
        detail=PAYLOAD,
        explanation=PAYLOAD,
    )
    out = tmp_path / "report.html"
    write_html_report([result], "ledger.csv", "bank.csv", str(out))

    html = out.read_text(encoding="utf-8")
    assert PAYLOAD not in html
    assert "&lt;img src=x onerror=&#34;alert(1)&#34;&gt;" in html
