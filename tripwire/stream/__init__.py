"""Streaming ingestion: replay a labeled corpus as a timestamped, blind event stream.

The detector sees only Events; GroundTruth is held aside and rejoined downstream to
score. See docs/threat_model.md §4 (streaming) and the honesty boundary in event.py.
"""

from .bus import Bus, InMemoryBus
from .event import Event, GroundTruth, split
from .producer import replay

__all__ = ["Bus", "InMemoryBus", "Event", "GroundTruth", "split", "replay"]
