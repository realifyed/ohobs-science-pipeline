"""Correlated JSON Lines for exposure and batch operations."""

import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

from . import __version__


class Events:
    """One log per execution, avoiding concurrent writes to the same file."""

    def __init__(self, work: Path, scope: str, *, job_id=None, input_id=None):
        self.run_id = uuid4().hex
        self.path = work / "events" / f"{scope}-{self.run_id}.jsonl"
        self.job_id = job_id
        self.input_id = input_id
        self.observation_id = None
        self.product_id = None
        self.clock = monotonic()

    def emit(self, event: str, **fields):
        # Callers pass status, digests, types, numbers and controlled names.
        # No arbitrary exception text, headers, configuration, or request payloads.
        row = {
            "schema_version": 1,
            "software": __version__,
            "utc": datetime.now(UTC).isoformat(),
            "elapsed_s": monotonic() - self.clock,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "input_id": self.input_id,
            "observation_id": self.observation_id,
            "product_id": self.product_id,
            "event": event,
            **fields,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
