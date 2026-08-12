"""Persistent two-pass CER workflow for audio transcription review."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from potato.audio_cer_review import normalize_cer_text, pairwise_cer


WORKFLOW_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _submission_sort_key(row: Dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("submitted_at") or "9999"), str(row.get("annotator") or ""))


def _selection_metadata(state: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Return stored selection details, deriving them for legacy finalized rows."""
    method = state.get("final_method")
    if method != "pair_cer" and state.get("selection_reason"):
        return state.get("selection_reason"), state.get("tie_breaker")

    winner = str(state.get("final_annotator") or "")
    submissions = list((state.get("submissions") or {}).values())
    if not winner:
        return None, None
    if method == "manual":
        reviewer = state.get("reviewed_by") or "管理员"
        return f"管理员 {reviewer} 选择标注员 {winner} 作为最终结果", None
    if method == "pair_cer":
        comparisons = state.get("comparisons") or []
        cer = comparisons[0].get("cer") if comparisons else None
        tie_breaker = (
            "earlier_submission"
            if any(row.get("submitted_at") for row in submissions)
            else "annotator_id"
        )
        cer_text = (
            f"双人 CER {float(cer):.2%} 达标"
            if cer is not None else "双人 CER 已达标"
        )
        return cer_text, tie_breaker
    if method != "three_way_medoid":
        return None, None

    scores = state.get("scores") or {}
    if winner not in scores:
        return None, None
    minimum = min(float(value) for value in scores.values())
    tied = [
        str(annotator) for annotator, value in scores.items()
        if abs(float(value) - minimum) < 1e-12
    ]
    if len(tied) == 1:
        return (
            f"标注员 {winner} 的总差异最小，因此系统选择 {winner} 作为最终结果",
            None,
        )
    tied_rows = [row for row in submissions if str(row.get("annotator")) in tied]
    tie_breaker = (
        "earlier_submission"
        if any(row.get("submitted_at") for row in tied_rows)
        else "annotator_id"
    )
    if tie_breaker == "earlier_submission":
        return (
            f"总差异并列，标注员 {winner} 提交时间更早，因此系统选择 {winner} 作为最终结果",
            tie_breaker,
        )
    return (
        f"总差异并列且提交时间不可确定，系统按标注员编号选择 {winner} 作为最终结果",
        tie_breaker,
    )


class AudioCerWorkflowStore:
    """Own the recording-level assignment, arbitration, and final-result state."""

    def __init__(self, output_dir: Any):
        self.root = Path(output_dir) / "admin_review"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "cer_workflow_state.json"
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": WORKFLOW_VERSION, "migration_complete": False, "recordings": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        value.setdefault("version", WORKFLOW_VERSION)
        value.setdefault("migration_complete", False)
        value.setdefault("recordings", {})
        return value

    def _save(self) -> None:
        handle, temp_path = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self._data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @staticmethod
    def _empty(recording_id: str) -> Dict[str, Any]:
        return {
            "recording_id": str(recording_id),
            "stage": "awaiting_initial_assignment",
            "initial_annotators": [],
            "third_annotator": None,
            "submissions": {},
            "comparisons": [],
            "scores": {},
            "final_annotator": None,
            "review_candidate": None,
            "final_method": None,
            "final_annotation": None,
            "finalized_at": None,
            "selection_reason": None,
            "tie_breaker": None,
            "reason": None,
            "history": [],
            "updated_at": utc_now(),
        }

    def get(self, recording_id: str) -> Dict[str, Any]:
        with self._lock:
            state = self._data["recordings"].get(str(recording_id))
            return copy.deepcopy(state if state is not None else self._empty(recording_id))

    def list_states(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._data["recordings"])

    def migration_complete(self) -> bool:
        return bool(self._data.get("migration_complete"))

    def mark_migration_complete(self) -> None:
        with self._lock:
            self._data["version"] = WORKFLOW_VERSION
            self._data["migration_complete"] = True
            self._save()

    def _put(self, state: Dict[str, Any], previous: Optional[Dict[str, Any]] = None,
             history_reason: Optional[str] = None) -> Dict[str, Any]:
        if previous is not None and history_reason:
            snapshot = {
                key: copy.deepcopy(value)
                for key, value in previous.items()
                if key != "history"
            }
            state.setdefault("history", copy.deepcopy(previous.get("history", [])))
            state["history"].append({
                "changed_at": utc_now(),
                "reason": history_reason,
                "state": snapshot,
            })
        state["updated_at"] = utc_now()
        self._data["recordings"][str(state["recording_id"])] = copy.deepcopy(state)
        self._save()
        return copy.deepcopy(state)

    def register_initial_assignments(
        self, recording_id: str, annotators: Iterable[str]
    ) -> Dict[str, Any]:
        users = list(dict.fromkeys(str(user) for user in annotators if str(user)))
        if len(users) != 2:
            raise ValueError("CER 首轮必须且只能分配两名不同的标注员")
        with self._lock:
            previous = self.get(recording_id)
            state = copy.deepcopy(previous)
            state["initial_annotators"] = users
            state["third_annotator"] = None
            state["stage"] = "awaiting_pair_submissions"
            state["reason"] = None
            return self._put(state, previous, "initial_assignment_changed")

    def set_third_annotator(self, recording_id: str, annotator: Optional[str]) -> Dict[str, Any]:
        with self._lock:
            previous = self.get(recording_id)
            state = copy.deepcopy(previous)
            state["third_annotator"] = str(annotator) if annotator else None
            state["stage"] = "awaiting_third_submission" if annotator else "waiting_third_assignment"
            state["reason"] = None if annotator else "暂无符合条件的第三位标注员"
            return self._put(state, previous, "third_assignment_changed")

    def note_submission(
        self,
        recording_id: str,
        annotator: str,
        text: str,
        annotation: Any,
        submitted_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            previous = self.get(recording_id)
            state = copy.deepcopy(previous)
            existing = state.setdefault("submissions", {}).get(str(annotator), {})
            state["submissions"][str(annotator)] = {
                "annotator": str(annotator),
                "submitted_at": existing.get("submitted_at") or submitted_at or utc_now(),
                "text": str(text or ""),
                "annotation": copy.deepcopy(annotation),
            }
            return self._put(state)

    def recalculate(
        self,
        recording_id: str,
        pair_threshold: float = 0.03,
        consensus_threshold: float = 0.08,
        history_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Recalculate the current stage. Assignment of C is handled by the caller."""
        with self._lock:
            previous = self.get(recording_id)
            if previous.get("stage") == "manual_finalized":
                return previous
            state = copy.deepcopy(previous)
            submissions = sorted(state.get("submissions", {}).values(), key=_submission_sort_key)
            state.update({
                "comparisons": [], "scores": {}, "final_annotator": None,
                "review_candidate": None, "final_method": None, "final_annotation": None,
                "finalized_at": None, "selection_reason": None,
                "tie_breaker": None, "reason": None,
            })

            if len(submissions) > 3:
                state["stage"] = "needs_manual_review"
                state["reason"] = "历史数据包含三份以上提交，需人工确认"
                return self._put(state, previous, history_reason)
            if not submissions:
                state["stage"] = (
                    "awaiting_pair_submissions" if state.get("initial_annotators")
                    else "awaiting_initial_assignment"
                )
                return self._put(state, previous, history_reason)
            if any(not normalize_cer_text(row.get("text")) for row in submissions):
                state["stage"] = "needs_manual_review"
                state["reason"] = "存在空白转写文本，禁止系统自动通过"
                return self._put(state, previous, history_reason)
            if len(submissions) == 1:
                state["stage"] = "awaiting_pair_submissions"
                return self._put(state, previous, history_reason)

            first, second = submissions[0], submissions[1]
            pair_score = pairwise_cer(first["text"], second["text"])
            state["comparisons"] = [{
                "annotators": [first["annotator"], second["annotator"]],
                "cer": pair_score,
                "threshold": float(pair_threshold),
                "passed": pair_score <= pair_threshold,
            }]
            if pair_score <= pair_threshold:
                winner = min((first, second), key=_submission_sort_key)
                pair_tie_breaker = (
                    "earlier_submission"
                    if any(row.get("submitted_at") for row in (first, second))
                    else "annotator_id"
                )
                state.update({
                    "stage": "auto_finalized",
                    "final_annotator": winner["annotator"],
                    "final_method": "pair_cer",
                    "final_annotation": copy.deepcopy(winner.get("annotation")),
                    "finalized_at": utc_now(),
                    "selection_reason": f"双人 CER {pair_score:.2%} 达标",
                    "tie_breaker": pair_tie_breaker,
                })
                return self._put(state, previous, history_reason)

            if len(submissions) == 2:
                state["stage"] = (
                    "awaiting_third_submission" if state.get("third_annotator")
                    else "waiting_third_assignment"
                )
                if not state.get("third_annotator"):
                    state["reason"] = "双人 CER 高于 3%，需要第三位标注员"
                return self._put(state, previous, history_reason)

            comparisons = []
            distances: Dict[tuple[str, str], float] = {}
            for left_index, left in enumerate(submissions):
                for right in submissions[left_index + 1:]:
                    score = pairwise_cer(left["text"], right["text"])
                    key = tuple(sorted((left["annotator"], right["annotator"])))
                    distances[key] = score
                    comparisons.append({
                        "annotators": [left["annotator"], right["annotator"]],
                        "cer": score,
                        "threshold": float(consensus_threshold),
                        "passed": score <= consensus_threshold,
                    })
            state["comparisons"] = comparisons
            scores = {}
            for row in submissions:
                user = row["annotator"]
                scores[user] = sum(
                    score for pair, score in distances.items() if user in pair
                )
            state["scores"] = scores
            minimum = min(scores.values())
            tied = [row for row in submissions if abs(scores[row["annotator"]] - minimum) < 1e-12]
            winner = min(tied, key=_submission_sort_key)
            tie_breaker = None
            if len(tied) > 1:
                submitted_at = [row.get("submitted_at") for row in tied]
                tie_breaker = (
                    "earlier_submission"
                    if any(value for value in submitted_at)
                    else "annotator_id"
                )
            if tie_breaker == "earlier_submission":
                selection_reason = (
                    f"总差异并列，标注员 {winner['annotator']} 提交时间更早，"
                    f"因此系统选择 {winner['annotator']} 作为最终结果"
                )
            elif tie_breaker == "annotator_id":
                selection_reason = (
                    f"总差异并列且提交时间不可确定，系统按标注员编号选择 "
                    f"{winner['annotator']} 作为最终结果"
                )
            else:
                selection_reason = (
                    f"标注员 {winner['annotator']} 的总差异最小，因此系统选择 "
                    f"{winner['annotator']} 作为最终结果"
                )
            if min(distances.values()) >= consensus_threshold:
                state.update({
                    "stage": "needs_manual_review",
                    "review_candidate": winner["annotator"],
                    "reason": "三组 CER 均高于 8%，需要管理员介入",
                    "selection_reason": selection_reason,
                    "tie_breaker": tie_breaker,
                })
                return self._put(state, previous, history_reason)

            state.update({
                "stage": "auto_finalized",
                "final_annotator": winner["annotator"],
                "review_candidate": winner["annotator"],
                "final_method": "three_way_medoid",
                "final_annotation": copy.deepcopy(winner.get("annotation")),
                "finalized_at": utc_now(),
                "selection_reason": selection_reason,
                "tie_breaker": tie_breaker,
            })
            return self._put(state, previous, history_reason)

    def finalize_manual(
        self, recording_id: str, annotator: str, annotation: Any, admin: str
    ) -> Dict[str, Any]:
        with self._lock:
            previous = self.get(recording_id)
            if str(annotator) not in previous.get("submissions", {}):
                raise ValueError("所选标注员没有提交该录音")
            state = copy.deepcopy(previous)
            state.update({
                "stage": "manual_finalized",
                "final_annotator": str(annotator),
                "final_method": "manual",
                "final_annotation": copy.deepcopy(annotation),
                "finalized_at": utc_now(),
                "reviewed_by": str(admin),
                "selection_reason": (
                    f"管理员 {admin} 选择标注员 {annotator} 作为最终结果"
                ),
                "tie_breaker": None,
                "reason": None,
            })
            return self._put(state, previous, "manual_finalized")

    def reopen_for_manual_review(self, recording_id: str, admin: str) -> Dict[str, Any]:
        with self._lock:
            previous = self.get(recording_id)
            if previous.get("stage") not in {"auto_finalized", "manual_finalized"}:
                raise ValueError("只有已定稿的录音可以重新编辑")
            state = copy.deepcopy(previous)
            state.update({
                "stage": "needs_manual_review",
                "final_annotator": None,
                "final_method": None,
                "final_annotation": None,
                "finalized_at": None,
                "selection_reason": None,
                "tie_breaker": None,
                "reason": "管理员重新打开审核",
                "reopened_by": str(admin),
            })
            return self._put(state, previous, "manual_reopened")

    def decorate_records(self, records: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
        result = []
        for record in records:
            row = dict(record)
            workflow = self.get(str(record["recording_id"]))
            selection_reason, tie_breaker = _selection_metadata(workflow)
            row.update({
                "workflow_stage": workflow.get("stage"),
                "workflow_reason": workflow.get("reason"),
                "workflow_comparisons": workflow.get("comparisons", []),
                "workflow_scores": workflow.get("scores", {}),
                "third_annotator": workflow.get("third_annotator"),
                "final_annotator": workflow.get("final_annotator"),
                "review_candidate": workflow.get("review_candidate"),
                "final_method": workflow.get("final_method"),
                "finalized_at": workflow.get("finalized_at"),
                "selection_reason": selection_reason,
                "tie_breaker": tie_breaker,
                "is_final_result": workflow.get("final_annotator") == record.get("annotator"),
            })
            result.append(row)
        return result

    def final_results(self) -> list[Dict[str, Any]]:
        results = []
        for state in self.list_states().values():
            if state.get("stage") not in {"auto_finalized", "manual_finalized"}:
                continue
            selection_reason, tie_breaker = _selection_metadata(state)
            results.append({
                "recording_id": state["recording_id"],
                "annotator": state.get("final_annotator"),
                "method": state.get("final_method"),
                "finalized_at": state.get("finalized_at"),
                "annotation": state.get("final_annotation"),
                "comparisons": state.get("comparisons", []),
                "scores": state.get("scores", {}),
                "selection_reason": selection_reason,
                "tie_breaker": tie_breaker,
            })
        return sorted(results, key=lambda row: row["recording_id"])
