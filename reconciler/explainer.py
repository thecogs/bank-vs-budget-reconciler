"""Turns the matcher's flags into plain-language explanations.

The matching decision itself is always deterministic (see matcher.py).
This module only adds a sentence of context on top of a flag that's
already been made — and it degrades gracefully with no API key set,
so `reconciler` is useful out of the box before you've wired up
billing. Set ANTHROPIC_API_KEY to turn it on.
"""

from __future__ import annotations

import json
import os
import sys
from typing import List

from reconciler.models import ReconciliationResult

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

_FALLBACK_ACTIONS = {
    "amount_mismatch": "Check the receipt for this one — the amounts don't agree.",
    "missing_in_ledger": "Add this to the ledger, or confirm it's a bank-side charge you're fine with.",
    "missing_in_bank": "Confirm this hasn't cleared yet, or check it wasn't entered twice.",
    "possible_duplicate_charge": "Likely worth a call to the vendor about a refund.",
}


def _fallback_explanation(result: ReconciliationResult) -> str:
    action = _FALLBACK_ACTIONS.get(result.flag, "Take a closer look.")
    return f"{result.detail} {action}"


def add_explanations(
    results: List[ReconciliationResult], model: str = DEFAULT_MODEL
) -> None:
    """Mutates `results` in place, filling in `.explanation`.

    Only flagged rows (severity != "ok") get sent to the model — clean
    matches don't need a sentence written about them, and it keeps the
    prompt (and the bill) small.
    """
    to_explain = [r for r in results if r.severity != "ok"]
    if not to_explain:
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        for r in to_explain:
            r.explanation = _fallback_explanation(r)
        return

    try:
        _explain_with_claude(to_explain, api_key, model)
    except Exception as exc:  # noqa: BLE001 - this is a deliberate, logged fallback
        print(
            f"[reconciler] LLM explanation call failed ({exc}); "
            "falling back to templated explanations.",
            file=sys.stderr,
        )
        for r in to_explain:
            if r.explanation is None:
                r.explanation = _fallback_explanation(r)


def _explain_with_claude(
    to_explain: List[ReconciliationResult], api_key: str, model: str
) -> None:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    items = [
        {
            "index": i,
            "flag": r.flag,
            "date": r.date_str,
            "description": r.description,
            "amount": r.amount,
            "detail": r.detail,
        }
        for i, r in enumerate(to_explain)
    ]

    prompt = (
        "You are helping someone reconcile their business bank account against "
        "their manually kept ledger. Below is a JSON list of flagged discrepancies "
        "a deterministic matcher already found — don't re-decide anything, just "
        "explain each one in one plain-language sentence a non-accountant would "
        "understand, and suggest what to do about it. Reply with ONLY a JSON array "
        "of objects: [{\"index\": <int>, \"explanation\": \"<one sentence, "
        "explanation + suggested action>\"}, ...], one entry per item, same order "
        "is not required but every index must appear exactly once.\n\n"
        f"{json.dumps(items, indent=2)}"
    )

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(block.text for block in message.content if block.type == "text")
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"Model reply had no JSON array: {text[:200]!r}")
    parsed = json.loads(text[start : end + 1])

    by_index = {item["index"]: item["explanation"] for item in parsed}
    for i, r in enumerate(to_explain):
        r.explanation = by_index.get(i) or _fallback_explanation(r)
