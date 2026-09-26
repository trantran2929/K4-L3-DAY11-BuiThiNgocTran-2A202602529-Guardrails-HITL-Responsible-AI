"""
Assignment 11 — Audit Log starter (TODO).

Records every interaction for forensics. Never blocks by itself —
other layers catch attacks; this layer makes them reviewable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import time


def default_audit_log_path() -> str:
    """Always resolve to <repo>/outputs/… (safe when cwd is src/)."""
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "outputs" / "audit_log.json")


class AuditLogPlugin:
    """Framework-agnostic audit logger (wire into ADK callbacks or your pipeline)."""

    def __init__(self):
        self.name = "audit_log"
        self.logs: list[dict] = []
        self._open: dict[str, float] = {}
        self._pending: dict[str, dict] = {}

    def record_input(self, *, user_id: str, text: str, request_id: str | None = None):
        """TODO: store input + start timestamp keyed by request_id/user_id."""
        # raise NotImplementedError("Implement AuditLogPlugin.record_input")
        key = request_id or user_id
        started_at = utc_now_iso()

        entry = {
            "request_id": request_id,
            "user_id": user_id,
            "input": text,
            "started_at": started_at,
            "output": None,
            "blocked": False,
            "layer": None,
            "completed_at": None,
            "latency_seconds": None,
        }

        self.logs.append(entry)
        self._pending[key] = entry
        self._open[key] = time.perf_counter()

    def record_output(
        self,
        *,
        user_id: str,
        text: str,
        blocked: bool = False,
        layer: str | None = None,
        request_id: str | None = None,
    ):
        """TODO: store output, layer decision, latency; append to self.logs."""
        # raise NotImplementedError("Implement AuditLogPlugin.record_output")
        key = request_id or user_id
        entry = self._pending.pop(key, None)
        started = self._open.pop(key, None)

        if entry is None:
            entry = {
                "request_id": request_id,
                "user_id": user_id,
                "input": None,
                "started_at": None,
            }
            self.logs.append(entry)

        entry.update({
            "output": text,
            "blocked": blocked,
            "layer": layer,
            "completed_at": utc_now_iso(),
            "latency_seconds": (
                round(time.perf_counter() - started, 6)
                if started is not None
                else None
            ),
        })

    def export_json(self, filepath: str | None = None):
        """Write logs to disk (JSON array) under repo-root ``outputs/`` by default."""
        # TODO: path = filepath or default_audit_log_path()
        #       ensure parent dirs exist, dump self.logs with indent=2
        # _ = filepath or default_audit_log_path()
        # raise NotImplementedError("Implement AuditLogPlugin.export_json")
        path = Path(filepath or default_audit_log_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.logs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
