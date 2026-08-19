"""Versioned execution manifests for reproducible EvalGauge runs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from .generate.schema import LabeledPrompt


class RunStatus(str, Enum):
    """Terminal states supported by the current all-or-nothing offline runner."""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class EvalRun:
    """Immutable description of one execution and the artifacts it used."""

    run_id: str
    status: RunStatus
    started_at: datetime
    completed_at: datetime
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    detector_version: str
    judge_model: str
    policy_version: str
    seed: int
    low_threshold: float
    high_threshold: float
    git_sha: str
    baseline_run_id: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.run_id,
            self.dataset_name,
            self.dataset_version,
            self.dataset_hash,
            self.detector_version,
            self.judge_model,
            self.policy_version,
            self.git_sha,
        )
        if any(not value.strip() for value in required):
            raise ValueError("run identity and artifact-version fields must be non-empty")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if not 0.0 <= self.low_threshold <= self.high_threshold <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= low <= high <= 1")
        if self.baseline_run_id == self.run_id:
            raise ValueError("a run cannot use itself as its baseline")

    @property
    def configuration_hash(self) -> str:
        """Fingerprint the evaluated artifacts/configuration, separate from execution ID."""

        configuration = {
            "dataset_hash": self.dataset_hash,
            "detector_version": self.detector_version,
            "git_sha": self.git_sha,
            "high_threshold": self.high_threshold,
            "judge_model": self.judge_model,
            "low_threshold": self.low_threshold,
            "policy_version": self.policy_version,
            "seed": self.seed,
        }
        payload = json.dumps(
            configuration, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def new_run_id() -> str:
    """Return an execution identity; identical configurations still get distinct runs."""

    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dataset_content_hash(prompts: Iterable[LabeledPrompt]) -> str:
    """Hash canonical prompt content plus truth/provenance, independent of object identity."""

    digest = hashlib.sha256()
    for prompt in prompts:
        record = {
            "family": prompt.family.value,
            "is_synthetic": prompt.is_synthetic,
            "label": prompt.label.value,
            "objective": prompt.objective,
            "source": prompt.source,
            "text": prompt.text,
        }
        digest.update(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def current_git_sha() -> str:
    """Resolve the code revision, allowing packaged/CI callers to provide it explicitly."""

    configured = os.environ.get("EVALGAUGE_GIT_SHA")
    if configured:
        return configured
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return f"{sha}-dirty" if dirty else sha
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown"
