"""EvalGauge — a data pipeline that measures what a jailbreak safeguard actually stops."""

from .runs import EvalRun, RunStatus

__all__ = ["EvalRun", "RunStatus"]
