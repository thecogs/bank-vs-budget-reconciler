"""Renders reconciliation results to an HTML report and a console summary."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from reconciler.models import ReconciliationResult

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def write_html_report(
    results: List[ReconciliationResult],
    ledger_path: str,
    bank_path: str,
    out_path: str,
) -> None:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("report.html.jinja")

    matched = [r for r in results if r.flag == "matched"]
    flagged = [r for r in results if r.flag != "matched"]
    flagged.sort(key=lambda r: {"error": 0, "warning": 1, "info": 2}.get(r.severity, 3))

    counts = {
        "matched": len(matched),
        "error": sum(1 for r in flagged if r.severity == "error"),
        "warning": sum(1 for r in flagged if r.severity == "warning"),
        "info": sum(1 for r in flagged if r.severity == "info"),
    }

    html = template.render(
        ledger_path=ledger_path,
        bank_path=bank_path,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        matched=matched,
        flagged=flagged,
        counts=counts,
    )
    Path(out_path).write_text(html, encoding="utf-8")


def print_console_summary(results: List[ReconciliationResult]) -> None:
    matched = [r for r in results if r.flag == "matched"]
    flagged = [r for r in results if r.flag != "matched"]
    by_flag: dict[str, int] = {}
    for r in flagged:
        by_flag[r.flag] = by_flag.get(r.flag, 0) + 1

    print(f"\n{len(matched)} matched, {len(flagged)} flagged\n")
    for flag, count in sorted(by_flag.items()):
        print(f"  {flag.replace('_', ' '):<26} {count}")
    print()
    for r in sorted(flagged, key=lambda r: {"error": 0, "warning": 1, "info": 2}.get(r.severity, 3)):
        marker = {"error": "!!", "warning": "! ", "info": "  "}.get(r.severity, "  ")
        print(f"  [{marker}] {r.date_str}  {r.amount:>10.2f}  {r.description}")
        print(f"        {r.explanation or r.detail}")
