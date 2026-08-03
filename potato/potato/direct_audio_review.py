"""Persistent claim and audit state for direct administrator audio review."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


class ReviewConflict(ValueError):
    """Raised when a review is owned by a different administrator."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DirectAudioReviewStore:
    def __init__(self, output_dir: Any):
        self.root = Path(output_dir) / "admin_review"
        self.history_dir = self.root / "history"
        self.state_path = self.root / "review_state.json"
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    @staticmethod
    def key(recording_id: str, annotator: str) -> str:
        return f"{recording_id}::{annotator}"

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        handle, temp_path = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self._state, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.state_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def get(self, recording_id: str, annotator: str) -> Dict[str, Any]:
        return dict(self._state.get(self.key(recording_id, annotator), {
            "status": "pending", "assigned_to": None, "assigned_at": None,
            "reviewed_by": None, "reviewed_at": None,
        }))

    def list_reviews(self, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for record in records:
            row = dict(record)
            state = self.get(record["recording_id"], record["annotator"])
            row.update({
                "review_status": state["status"],
                "assigned_to": state.get("assigned_to"),
                "assigned_at": state.get("assigned_at"),
                "reviewed_by": state.get("reviewed_by"),
                "reviewed_at": state.get("reviewed_at"),
            })
            result.append(row)
        return result

    def claim(self, recording_id: str, annotator: str, admin: str) -> Dict[str, Any]:
        with self._lock:
            state = self.get(recording_id, annotator)
            owner = state.get("assigned_to")
            if owner and owner != admin:
                raise ReviewConflict("该审核任务已分配给其他管理员")
            state.update({"status": "in_progress", "assigned_to": admin,
                          "assigned_at": state.get("assigned_at") or _now()})
            self._state[self.key(recording_id, annotator)] = state
            self._save()
            return dict(state)

    def _require_owner(self, recording_id: str, annotator: str, admin: str) -> Dict[str, Any]:
        state = self.get(recording_id, annotator)
        if state.get("assigned_to") != admin:
            raise ReviewConflict("请先把该审核任务分配给自己")
        return state

    def require_editable(self, recording_id: str, annotator: str, admin: str) -> Dict[str, Any]:
        state = self.get(recording_id, annotator)
        owner = state.get("assigned_to")
        if state.get("status") == "pending" and not owner:
            return state
        if state.get("status") == "in_progress" and owner == admin:
            return state
        if owner and owner != admin:
            raise ReviewConflict("该审核任务已分配给其他管理员")
        raise ReviewConflict("当前审核状态不能修改")

    def complete(self, recording_id: str, annotator: str, admin: str) -> Dict[str, Any]:
        with self._lock:
            state = self.require_editable(recording_id, annotator, admin)
            state.update({"status": "completed", "reviewed_by": admin,
                          "reviewed_at": _now()})
            self._state[self.key(recording_id, annotator)] = state
            self._save()
            return dict(state)

    def reopen(self, recording_id: str, annotator: str, admin: str) -> Dict[str, Any]:
        with self._lock:
            state = self.get(recording_id, annotator)
            if state.get("assigned_to") not in (None, admin):
                raise ReviewConflict("该审核任务已分配给其他管理员")
            if state.get("reviewed_by") != admin:
                raise ReviewConflict("只有原审核人可以重新编辑")
            state.update({"status": "in_progress", "assigned_to": admin,
                          "assigned_at": state.get("assigned_at") or _now(),
                          "reviewed_at": None})
            self._state[self.key(recording_id, annotator)] = state
            self._save()
            return dict(state)

    def record_snapshot(self, recording_id: str, annotator: str,
                        admin: str, old_value: Any) -> Dict[str, Any]:
        snapshot = {
            "snapshot_id": uuid.uuid4().hex,
            "recording_id": recording_id,
            "annotator": annotator,
            "admin": admin,
            "created_at": _now(),
            "old_value": old_value,
        }
        path = self.history_dir / f"{snapshot['created_at'].replace(':', '-')}-{snapshot['snapshot_id']}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot
