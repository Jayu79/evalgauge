"""Two-tier detection: a fast surface classifier, then a Claude-as-judge on the ambiguous middle."""

from .detector import TwoTierDetector
from .fast import FastClassifier
from .judge import ClaudeJudge, Judge, JudgeResult, StubJudge
from .schema import Band, Detection

__all__ = [
    "FastClassifier", "Judge", "JudgeResult", "StubJudge", "ClaudeJudge",
    "TwoTierDetector", "Detection", "Band",
]
