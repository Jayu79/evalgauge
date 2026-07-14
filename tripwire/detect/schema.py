"""The detector's output contract — one row per event, mapping to dbt `stg_detections`.

Everything the measurement layer needs to attribute a decision: the tier-1 score, which
band it fell in, whether it was escalated, the judge's verdict (if any), the final call,
and the cost/latency that call incurred. `mtr_tier_contribution` reads exactly this to
answer "what did each tier catch, and what did it cost."
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Band(str, Enum):
    """Which side of the two thresholds the tier-1 score fell on."""

    CLEAR_BENIGN = "clear_benign"   # score < low  → pass, no judge
    AMBIGUOUS = "ambiguous"         # low ≤ score ≤ high → escalate to the judge
    CLEAR_ATTACK = "clear_attack"   # score > high → flag, no judge


@dataclass(frozen=True)
class Detection:
    """One event's detection result. Immutable; carries no ground truth (still blind)."""

    event_id: str
    tier1_score: float
    tier1_band: Band
    tier1_flag: bool            # tier-1's standalone call (score > high) — for the tier-1-only baseline
    escalated_to_judge: bool
    judge_verdict: bool | None  # None if not escalated; True = the judge called it an attack
    final_flag: bool            # the system's final decision (block or not)
    decided_by: str             # "fast" | "judge" — which tier produced final_flag
    latency_ms: float           # total per-event latency (tier-1 + judge if escalated)
    judge_cost_usd: float       # 0.0 when not escalated — cost is bounded to the middle band
    judge_rationale: str | None = None
    judge_model: str | None = None
