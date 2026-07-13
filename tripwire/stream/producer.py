"""The replay producer — turns a static corpus into a timestamped event stream.

We have no live traffic, so we *replay*: read the labeled corpus, assign each record an
event_id and an arrival timestamp, split it into a blind Event + held-aside GroundTruth,
publish the Event to the bus, and route the GroundTruth to a separate sink. Replaying
recorded/synthetic data through the live path is a standard way to exercise a streaming
system deterministically.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from ..generate.schema import LabeledPrompt
from .bus import Bus
from .event import GroundTruth, split

TruthSink = Callable[[GroundTruth], None]

# A fixed epoch so replays are reproducible (same corpus + same settings → same timestamps).
DEFAULT_START = datetime(2026, 1, 1, 0, 0, 0)


def replay(
    corpus: Iterable[LabeledPrompt],
    bus: Bus,
    truth_sink: TruthSink,
    *,
    start: datetime = DEFAULT_START,
    interval_ms: int = 100,
    realtime: bool = False,
) -> int:
    """Replay `corpus` as a stream. Returns the number of events emitted.

    - event_id is a zero-padded sequential counter → deterministic and human-readable.
    - ts advances by `interval_ms` per event → a synthetic but ordered arrival clock.
    - realtime=True actually sleeps between events (for the live dashboard); False emits
      as fast as possible with the same synthetic timestamps (for warehouse loading).

    Note the ordering inside the loop: GroundTruth is routed to its sink *before* the
    Event is published. The detector (a subscriber) must never be able to observe the
    truth — the two paths never touch here; they only rejoin later in the warehouse.
    """
    n = 0
    for i, prompt in enumerate(corpus):
        event_id = f"evt-{i:06d}"
        ts = start + timedelta(milliseconds=i * interval_ms)
        event, truth = split(prompt, event_id=event_id, ts=ts)

        truth_sink(truth)      # answer key, held aside
        bus.publish(event)     # blind event, to whoever is subscribed (the detector)

        if realtime:
            time.sleep(interval_ms / 1000)
        n += 1
    return n
