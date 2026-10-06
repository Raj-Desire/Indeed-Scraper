"""Metrics for comparing match scores against human-labelled expectations."""

from __future__ import annotations

from typing import Optional

from app.config.constants import score_to_priority

BANDS = ["High", "Medium", "Low"]
BAND_MIDPOINT = {"High": 85, "Medium": 55, "Low": 20}


def normalize_label(label: str) -> Optional[str]:
    l = (label or "").strip().lower()
    return {"high": "High", "good": "High", "h": "High", "medium": "Medium", "med": "Medium", "m": "Medium",
            "low": "Low", "bad": "Low", "l": "Low"}.get(l)


def evaluate(rows: list[dict]) -> dict:
    """rows: [{'expected': 'High'|'Medium'|'Low', 'score': int|None}, ...]

    Unscored rows (score None) are excluded from accuracy/error but reported as a rate.
    """
    scored = [r for r in rows if r.get("score") is not None and r.get("expected") in BANDS]
    total = len([r for r in rows if r.get("expected") in BANDS])
    confusion = {e: {p: 0 for p in BANDS} for e in BANDS}
    abs_err = 0.0
    for r in scored:
        pred = score_to_priority(r["score"])
        confusion[r["expected"]][pred] += 1
        abs_err += abs(r["score"] - BAND_MIDPOINT[r["expected"]])

    n = len(scored)
    correct = sum(confusion[b][b] for b in BANDS)
    tp = confusion["High"]["High"]
    pred_high = sum(confusion[e]["High"] for e in BANDS)
    actual_high = sum(confusion["High"].values())
    # The costly error for sales: a Low-fit job flagged High wastes outreach.
    false_high = confusion["Low"]["High"]
    actual_low = sum(confusion["Low"].values())
    return {
        "labelled": total,
        "scored": n,
        "unscored_rate": round(1 - n / total, 3) if total else 0.0,
        "band_accuracy": round(correct / n, 3) if n else 0.0,
        "high_precision": round(tp / pred_high, 3) if pred_high else 0.0,
        "high_recall": round(tp / actual_high, 3) if actual_high else 0.0,
        "low_flagged_high_rate": round(false_high / actual_low, 3) if actual_low else 0.0,
        "mae_vs_band_midpoint": round(abs_err / n, 1) if n else 0.0,
        "confusion": confusion,
    }
