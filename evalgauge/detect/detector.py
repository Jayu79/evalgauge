"""The two-tier detector — the piece that makes the two tiers one system.

Flow, per blind Event:

    tier-1 score ─┬─ score < low   → clear-benign → pass          (decided by fast)
                  ├─ score > high  → clear-attack → flag          (decided by fast)
                  └─ otherwise     → ambiguous → ask the judge → judge decides

The two thresholds are the tunable knob. Widen the gap → more prompts escalate → better
detection at higher cost/latency; narrow it → cheaper and faster but more mistakes slip
past tier-1 alone. Where they sit is a real operating-point choice, and the whole point of
EvalGauge is to measure catch rate AND false-positive burden *together* as you move them
(the Pareto sweep in the failure-analysis phase). Defaults here are grounded in the
held-out score distributions, where hard negatives and disguised attacks overlap ~0.56–0.85.
"""

from __future__ import annotations

import time

from ..stream.event import Event
from .fast import FastClassifier
from .judge import Judge
from .schema import Band, Detection

DEFAULT_LOW = 0.5   # below this, tier-1 is confident-benign
DEFAULT_HIGH = 0.85  # above this, tier-1 is confident-attack; between = escalate


class TwoTierDetector:
    """Fast surface tier + judge, joined by a two-threshold escalation rule.

    The fast classifier must already be fit (trained offline on the train split). The judge
    is any object honoring the Judge protocol — real ClaudeJudge or the offline StubJudge.
    """

    def __init__(
        self,
        fast: FastClassifier,
        judge: Judge,
        *,
        low: float = DEFAULT_LOW,
        high: float = DEFAULT_HIGH,
    ) -> None:
        if not 0.0 <= low <= high <= 1.0:
            raise ValueError(f"need 0 <= low <= high <= 1, got low={low} high={high}")
        self.fast = fast
        self.judge = judge
        self.low = low
        self.high = high

    def detect(self, event: Event) -> Detection:
        start = time.perf_counter()
        score = self.fast.score(event.text)

        if score < self.low:
            band = Band.CLEAR_BENIGN
        elif score > self.high:
            band = Band.CLEAR_ATTACK
        else:
            band = Band.AMBIGUOUS

        tier1_flag = score > self.high  # what tier-1 would decide alone at the high threshold

        if band is Band.AMBIGUOUS:
            verdict = self.judge.judge(event.text)  # only the middle band pays the judge
            return Detection(
                event_id=event.event_id,
                tier1_score=score,
                tier1_band=band,
                tier1_flag=tier1_flag,
                escalated_to_judge=True,
                judge_verdict=verdict.is_attack,
                final_flag=verdict.is_attack,
                decided_by="judge",
                latency_ms=(time.perf_counter() - start) * 1000,
                judge_cost_usd=verdict.cost_usd,
                judge_rationale=verdict.rationale,
                judge_model=verdict.model,
            )

        # clear-benign or clear-attack: tier-1 decides, no judge cost
        return Detection(
            event_id=event.event_id,
            tier1_score=score,
            tier1_band=band,
            tier1_flag=tier1_flag,
            escalated_to_judge=False,
            judge_verdict=None,
            final_flag=(band is Band.CLEAR_ATTACK),
            decided_by="fast",
            latency_ms=(time.perf_counter() - start) * 1000,
            judge_cost_usd=0.0,
        )
