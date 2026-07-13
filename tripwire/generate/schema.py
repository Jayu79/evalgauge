"""The data contract for every labeled prompt Tripwire produces.

Design intent: define the *shape* of the output before any generation logic. Every
prompt — synthetic or from a public corpus — obeys this contract, which is what lets
the stream, detector, warehouse, and dbt layers stay decoupled: they agree on this
record, not on how it was made.

The fields here map directly onto dbt's `stg_events`. That is deliberate. Provenance
stamped at birth (family, label, source) is what makes per-family, per-source
measurement possible downstream — see docs/threat_model.md §7.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum


class Family(str, Enum):
    """The attack surface from threat_model.md §3, plus the benign control group.

    Grouped by *where the malicious signal lives* — the property that decides
    whether a surface-level detector can see it at all.
    """

    # Group I — signal is local & recognizable (the fast tier's home turf)
    ROLE_PLAY = "role-play / persona"
    PREFIX_INJECTION = "prefix-injection"
    # Group II — signal is disguised or distributed (only intent-understanding survives)
    ENCODING = "encoding / obfuscation"
    MANY_SHOT = "many-shot"
    GRADUAL_ESCALATION = "gradual escalation"
    # Group III — signal is unprecedented (the frontier)
    NOVEL = "novel (synthetic)"
    # The control group — not an attack. Its whole job is to be the FP-burden denominator.
    BENIGN = "benign"


class Label(str, Enum):
    """Ground truth. Known *only* because we generated (or hand-labeled) the data.

    This is the entire basis for Tripwire's honesty boundary: it reports precision/
    recall as a *controlled* measurement over labeled data, and makes no claim about
    live unlabeled traffic (threat_model.md §0, §7).
    """

    ATTACK = "attack"
    BENIGN = "benign"


@dataclass(frozen=True)
class LabeledPrompt:
    """One labeled prompt with full provenance. Immutable once created."""

    text: str            # the prompt itself, as the detector would see it
    family: Family       # which attack family (or BENIGN) — the per-family reporting key
    label: Label         # ground truth: attack or benign
    is_synthetic: bool   # True = we generated it; False = from a public corpus
    source: str          # provenance: e.g. "synthetic:role_play.v1" or "corpus:advbench"
    objective: str       # the *benign stand-in* goal the example wraps (see §6)

    @property
    def prompt_hash(self) -> str:
        """Stable 16-char id for the prompt text. Lets the warehouse dedupe and
        reference a prompt without storing it in the clear everywhere."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]

    def __post_init__(self) -> None:
        # A benign family must carry a benign label, and vice-versa. Catch
        # contract violations at creation, not three layers downstream.
        is_benign_family = self.family is Family.BENIGN
        is_benign_label = self.label is Label.BENIGN
        if is_benign_family != is_benign_label:
            raise ValueError(
                f"label/family mismatch: family={self.family} label={self.label}"
            )
