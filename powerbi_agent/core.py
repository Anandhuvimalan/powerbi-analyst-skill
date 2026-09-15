from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class BuildError(Exception):
    """Actionable failure; never interpreted as successful validation."""


def identity(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:20]


def identifier(value: str) -> str:
    value = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE).strip("_")
    return value or "Table"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def within(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise BuildError(f"Project path escapes its directory: {relative}")
    return target


@dataclass
class ProjectState:
    project_path: str
    business_objective: str
    source_files: list = field(default_factory=list)
    dataset_profile: list = field(default_factory=list)
    analysis_brief: dict = field(default_factory=dict)
    domain: str = "general"
    model_plan: dict = field(default_factory=dict)
    report_plan: dict = field(default_factory=dict)
    validation_results: list = field(default_factory=list)
    screenshots: list = field(default_factory=list)
    qa_scores: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    events: list = field(default_factory=list)
    iteration_count: int = 0
    status: str = "planning"

    def save(self, path: Path) -> None:
        write_json(path, asdict(self))

    def log(self, phase: str, message: str) -> None:
        event = {"phase": phase, "message": message}
        self.events.append(event)
        print(f"[{phase}] {message}", flush=True)
