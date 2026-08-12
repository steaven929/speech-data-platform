"""Persistent state and audit history for direct administrator audio review."""

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
    """Raised when a review operation is invalid for the current state."""


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
            if not isinstance(data, dict):
                return {}
            for state in data.values():
                if isinstance(state, dict) and state.get("status") == "pending":
                    state["status"] = "in_progress"
            return data
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
        state = dict(self._state.get(self.key(recording_id, annotator), {
            "status": "in_progress", "assigned_to": None, "assigned_at": None,
            "reviewed_by": None, "reviewed_at": None,
        }))
        if state.get("status") == "pending":
            state["status"] = "in_progress"
        return state

    def list_reviews(self, records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for record in records:
            row = dict(record)
            state = self.get(record["recording_id"], record["annotator"])
            row.update({
                "review_status": state["status"],
                "assigned_to": state.get("assigned_to"),
                "assigned_at": state.get("assigned_at"),
                "pushed_at": state.get("pushed_at") or record.get("submitted_at"),
                "reviewed_by": state.get("reviewed_by"),
                "reviewed_at": state.get("reviewed_at"),
                "review_method": state.get("review_method"),
                "cer_score": state.get("cer_score"),
                "qc_reason": state.get("qc_reason"),
            })
            result.append(row)
        return result

    def require_editable(self, recording_id: str, annotator: str, admin: str) -> Dict[str, Any]:
        state = self.get(recording_id, annotator)
        if state.get("status") == "in_progress":
            return state
        raise ReviewConflict("当前审核状态不能修改")

    def complete(self, recording_id: str, annotator: str, admin: str) -> Dict[str, Any]:
        with self._lock:
            state = self.require_editable(recording_id, annotator, admin)
            state.update({"status": "completed", "reviewed_by": admin,
                          "reviewed_at": _now(), "review_method": "manual",
                          "cer_score": None, "qc_reason": None})
            self._state[self.key(recording_id, annotator)] = state
            self._save()
            return dict(state)

    def record_auto_rejection(self, recording_id: str, annotator: str,
                              reason: str) -> Dict[str, Any]:
        """Persist a zero-change rejection without exposing it as review work."""
        with self._lock:
            state = self.get(recording_id, annotator)
            state.update({
                "status": "in_progress",
                "reviewed_by": None,
                "reviewed_at": None,
                "review_method": "system_rejected",
                "cer_score": 0.0,
                "qc_reason": reason,
                "rejected_at": _now(),
                "reject_count": int(state.get("reject_count", 0)) + 1,
            })
            self._state[self.key(recording_id, annotator)] = state
            self._save()
            return dict(state)

    def reconcile_auto_matches(self, recording_id: str, annotators: Iterable[str],
                               comparisons: Iterable[Dict[str, Any]],
                               threshold: float) -> List[str]:
        """Apply system completion to exactly the annotators in passing pairs."""
        recording_id = str(recording_id)
        matched = {str(annotator) for annotator in annotators}
        comparison_rows = list(comparisons)
        with self._lock:
            prefix = f"{recording_id}::"
            for key, state in self._state.items():
                if (key.startswith(prefix) and state.get("status") == "completed"
                        and state.get("review_method") == "cer"):
                    state.update({
                        "status": "in_progress", "reviewed_by": None,
                        "reviewed_at": None, "review_method": None,
                        "cer_score": None, "qc_reason": None,
                    })

            completed_at = _now()
            for annotator in matched:
                relevant_scores = [
                    float(row["cer"]) for row in comparison_rows
                    if row.get("passed") and annotator in row.get("annotators", [])
                ]
                state = self.get(recording_id, annotator)
                if (state.get("status") == "completed"
                        and state.get("review_method") == "manual"):
                    continue
                state.update({
                    "status": "completed",
                    "reviewed_by": "system:cer",
                    "reviewed_at": completed_at,
                    "review_method": "cer",
                    "cer_score": min(relevant_scores) if relevant_scores else None,
                    "cer_threshold": float(threshold),
                    "qc_reason": "两名及以上标注员文本一致性达标，系统自动通过",
                })
                self._state[self.key(recording_id, annotator)] = state
            self._save()
        return sorted(matched)

    def reopen(self, recording_id: str, annotator: str, admin: str) -> Dict[str, Any]:
        with self._lock:
            state = self.get(recording_id, annotator)
            if state.get("status") != "completed":
                raise ReviewConflict("只有已完成的审核可以重新编辑")
            state.update({"status": "in_progress", "reviewed_at": None,
                          "review_method": None, "cer_score": None,
                          "qc_reason": None, "reopened_by": admin,
                          "reopened_at": _now()})
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

    def sync_workflow_state(self, workflow: Dict[str, Any]) -> None:
        """Project a recording-level CER decision onto legacy per-user rows.

        The direct-review API remains backward compatible, while the workflow
        store is the source of truth for whether a recording needs human work.
        Previous manual/system decisions are retained inline as audit history.
        """
        recording_id = str(workflow.get("recording_id", ""))
        participants = set((workflow.get("submissions") or {}).keys())
        participants.update(workflow.get("initial_annotators") or [])
        if workflow.get("third_annotator"):
            participants.add(str(workflow["third_annotator"]))
        stage = workflow.get("stage")
        finalized = stage in {"auto_finalized", "manual_finalized"}
        with self._lock:
            for annotator in participants:
                key = self.key(recording_id, annotator)
                state = self.get(recording_id, annotator)
                old_decision = {
                    name: state.get(name)
                    for name in (
                        "status", "reviewed_by", "reviewed_at", "review_method",
                        "cer_score", "qc_reason",
                    )
                }
                new_decision = {
                    "status": "completed" if finalized else "in_progress",
                    "reviewed_by": (
                        workflow.get("reviewed_by")
                        if stage == "manual_finalized" else
                        ("system:cer" if finalized else None)
                    ),
                    "reviewed_at": workflow.get("finalized_at") if finalized else None,
                    "review_method": workflow.get("final_method") if finalized else None,
                    "cer_score": min(
                        (float(row["cer"]) for row in workflow.get("comparisons", [])),
                        default=None,
                    ) if finalized else None,
                    "qc_reason": workflow.get("reason"),
                }
                if old_decision != new_decision and any(old_decision.values()):
                    history = state.setdefault("workflow_history", [])
                    history.append({"changed_at": _now(), "decision": old_decision})
                state.update(new_decision)
                state["workflow_stage"] = stage
                state["is_final_result"] = (
                    workflow.get("final_annotator") == str(annotator)
                )
                submission = (workflow.get("submissions") or {}).get(str(annotator)) or {}
                if submission.get("submitted_at"):
                    state["pushed_at"] = submission.get("submitted_at")
                self._state[key] = state
            self._save()
