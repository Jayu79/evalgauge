"""Assemble reproducible labeled corpora from the family generators, and (de)serialize them.

Three responsibilities, each a concept the rest of the pipeline depends on:

1. Controlled distribution — the corpus mix is a *measurement design choice*, not an
   attempt to mimic production traffic. See DEFAULT_SPEC.
2. Reproducibility — one seed regenerates the exact corpus, so a metric that moves
   downstream can only be the detector changing, never the data shifting under us.
3. Serialization — JSONL, because the stream replays record-by-record and our prompts
   contain newlines (many-shot, escalation) that would break CSV.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from pathlib import Path

from .families import GENERATORS
from .schema import Family, Label, LabeledPrompt

# The corpus distribution. This is deliberately NOT production's ~99.9%-benign mix.
# We *stratify*: oversample attacks so every family has enough examples to estimate
# its catch rate with real statistical power. If we mirrored production, a rare family
# might get 3 examples and its catch rate would be statistical noise. Re-weighting back
# to production base rates (for FP-burden reporting) happens downstream in dbt — the
# provenance we stamped (family, label) is exactly what makes that re-weighting possible.
DEFAULT_SPEC: dict[Family, int] = {
    Family.ROLE_PLAY: 200,
    Family.PREFIX_INJECTION: 200,
    Family.ENCODING: 200,
    Family.MANY_SHOT: 200,
    Family.GRADUAL_ESCALATION: 200,
    Family.NOVEL: 200,
    Family.BENIGN: 600,  # the control group — the FP-burden denominator (Asset B)
}


def build_corpus(
    spec: dict[Family, int] | None = None, *, seed: int = 0, split: str = "all"
) -> list[LabeledPrompt]:
    """Build a labeled corpus following `spec`, reproducible for a given `seed`.

    One seeded RNG is threaded through every generator, so (spec, seed, split) fully
    determines the output — the reproducibility guarantee the whole measurement
    story rests on.

    `split` selects disjoint phrasing pools: train on split="train", measure on
    split="eval", so the detector is scored on templates it never trained on — the
    only honest test (see families.py and docs/threat_model.md §2, §5).
    """
    spec = spec or DEFAULT_SPEC
    rng = random.Random(seed)
    corpus: list[LabeledPrompt] = []
    for family, n in spec.items():
        corpus.extend(GENERATORS[family](n, rng, split))
    # Interleave families so a replayed stream isn't 200 role-plays then 200 encodings —
    # a blocky stream would make the live dashboard misleading. Shuffle is seeded, so
    # still deterministic.
    rng.shuffle(corpus)
    return corpus


def _to_dict(p: LabeledPrompt) -> dict:
    return {
        "text": p.text,
        "family": p.family.value,
        "label": p.label.value,
        "is_synthetic": p.is_synthetic,
        "source": p.source,
        "objective": p.objective,
        "prompt_hash": p.prompt_hash,  # denormalized (derivable) — convenience for the warehouse
    }


def write_jsonl(prompts: Iterable[LabeledPrompt], path: str | Path) -> int:
    """Write one JSON object per line. Returns the count written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for p in prompts:
            f.write(json.dumps(_to_dict(p), ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: str | Path) -> list[LabeledPrompt]:
    """Read a JSONL corpus back into LabeledPrompts (prompt_hash recomputes itself)."""
    out: list[LabeledPrompt] = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out.append(
                LabeledPrompt(
                    text=d["text"],
                    family=Family(d["family"]),
                    label=Label(d["label"]),
                    is_synthetic=d["is_synthetic"],
                    source=d["source"],
                    objective=d["objective"],
                )
            )
    return out


def summarize(corpus: list[LabeledPrompt]) -> dict[str, int]:
    """Counts per family — for verification and for the reproducibility check."""
    counts: dict[str, int] = {}
    for p in corpus:
        counts[p.family.value] = counts.get(p.family.value, 0) + 1
    return counts


if __name__ == "__main__":
    # `python -m evalgauge.generate.corpus` → build the default corpus and write it.
    corpus = build_corpus(seed=42)
    n = write_jsonl(corpus, "data/corpus.jsonl")
    print(f"wrote {n} prompts to data/corpus.jsonl")
    for fam, c in summarize(corpus).items():
        print(f"  {fam:24} {c}")
