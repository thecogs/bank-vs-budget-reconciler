"""Command-line entrypoint.

    python -m reconciler.cli --bank data/sample_bank_export.csv \
        --ledger data/sample_ledger.csv --out report.html
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from reconciler.explainer import add_explanations
from reconciler.loader import load_bank, load_ledger
from reconciler.matcher import reconcile
from reconciler.report import print_console_summary, write_html_report


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Reconcile a bank export against a ledger.")
    parser.add_argument("--bank", default="data/sample_bank_export.csv", help="Bank export CSV")
    parser.add_argument("--ledger", default="data/sample_ledger.csv", help="Ledger CSV")
    parser.add_argument("--out", default="report.html", help="HTML report output path")
    parser.add_argument(
        "--no-explain", action="store_true", help="Skip LLM explanations even if a key is set"
    )
    args = parser.parse_args(argv)

    ledger = load_ledger(args.ledger)
    bank = load_bank(args.bank)
    results = reconcile(ledger, bank)

    if not args.no_explain:
        add_explanations(results)

    print_console_summary(results)
    write_html_report(results, args.ledger, args.bank, args.out)
    print(f"Full report written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
