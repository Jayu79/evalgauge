"""The stream's data models — and the honesty boundary that keeps the detector blind.

At the stream boundary, every labeled corpus record is split into two objects:

- Event       — ONLY what a real inbound prompt carries (id, time, text). The detector
                sees this and nothing else. There is no label here, on purpose.
- GroundTruth — the answer key (family, label, ...), held aside and keyed by event_id.
                It is joined back downstream to *score* the detector, never shown to it.

This split is why Tripwire's measurements are trustworthy: the detector cannot cheat,
because the truth is structurally out of its reach until after it has committed. In
production the GroundTruth simply would not exist (traffic is unlabeled) — see
docs/threat_model.md §0/§7.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..generate.schema import Family, Label, LabeledPrompt


@dataclass(frozen=True)
class Event:
    """What the detector receives — the production-realistic surface of a prompt.

    Deliberately minimal: an id, when it arrived, the text, and a content hash. No
    family, no label, no 'is_synthetic'. If it isn't here, a real inbound prompt
    wouldn't have it either.
    """

    event_id: str      # stream-assigned identity (generation stamped provenance; the stream stamps this)
    ts: datetime       # when the event "arrived" in the stream
    prompt_hash: str   # content fingerprint (matches LabeledPrompt.prompt_hash)
    text: str          # the prompt itself — the only signal the detector may use


@dataclass(frozen=True)
class GroundTruth:
    """The held-aside answer key for one event. Keyed by event_id; never given to the detector."""

    event_id: str
    family: Family
    label: Label
    is_synthetic: bool
    source: str
    objective: str


def split(prompt: LabeledPrompt, *, event_id: str, ts: datetime) -> tuple[Event, GroundTruth]:
    """Split a labeled corpus record into the blind Event and its held-aside GroundTruth.

    The same event_id ties them together so the warehouse can rejoin prediction to
    truth later — the one and only place the two are allowed to meet.
    """
    event = Event(
        event_id=event_id,
        ts=ts,
        prompt_hash=prompt.prompt_hash,
        text=prompt.text,
    )
    truth = GroundTruth(
        event_id=event_id,
        family=prompt.family,
        label=prompt.label,
        is_synthetic=prompt.is_synthetic,
        source=prompt.source,
        objective=prompt.objective,
    )
    return event, truth
