"""Synthetic labeled-prompt generation with provenance. See docs/threat_model.md §3, §6."""

from .schema import Family, Label, LabeledPrompt

__all__ = ["Family", "Label", "LabeledPrompt"]
