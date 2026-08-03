"""Read and export persisted audio annotations for the admin dashboard."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _audio_annotation_value(labels: Dict[Any, Any]) -> Optional[Any]:
    for label, value in (labels or {}).items():
        if hasattr(label, "get_schema") and hasattr(label, "get_name"):
            schema_name = str(label.get_schema())
            label_name = str(label.get_name())
        elif hasattr(label, "schema") and hasattr(label, "name"):
            schema_name = str(label.schema)
            label_name = str(label.name)
        else:
            key = str(label)
            if ":::" in key:
                schema_name, label_name = key.split(":::", 1)
            elif ":" in key:
                schema_name, label_name = key.split(":", 1)
            else:
                continue
        if schema_name == "transcript_segments" and label_name == "_data":
            return value
    return None


def _normalise_segment(segment: Dict[str, Any]) -> Dict[str, Any]:
    annotations = segment.get("annotations")
    if not isinstance(annotations, dict):
        annotations = {}
    return {
        "id": str(segment.get("id", "")),
        "start_time": float(segment.get("start_time", 0)),
        "end_time": float(segment.get("end_time", 0)),
        "speaker": str(segment.get("label", "")),
        "text": str(segment.get("text", "")),
        "is_dialect": bool(annotations.get("dialect", False)),
    }


def _record_from_value(
    recording_id: Any, annotator: Any, value: Any
) -> Dict[str, Any]:
    record = {
        "recording_id": str(recording_id),
        "annotator": str(annotator),
        "segment_count": 0,
        "segments": [],
        "parse_error": None,
    }
    try:
        data = json.loads(value) if isinstance(value, str) else value
        if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
            raise ValueError("missing segments")
        segments = [
            _normalise_segment(segment)
            for segment in data["segments"]
            if isinstance(segment, dict)
        ]
        segments.sort(key=lambda segment: (segment["start_time"], segment["end_time"]))
        record["segments"] = segments
        record["segment_count"] = len(segments)
    except (TypeError, ValueError, json.JSONDecodeError):
        record["parse_error"] = "标注数据格式错误"
    return record


def collect_audio_annotation_records(user_state_manager: Any) -> List[Dict[str, Any]]:
    """Return stable records for every persisted audio annotation."""
    records = []
    for username in sorted(user_state_manager.get_user_ids()):
        user_state = user_state_manager.get_user_state(username)
        if not user_state:
            continue
        for recording_id, annotations in user_state.get_all_annotations().items():
            labels = annotations.get("labels", {}) if isinstance(annotations, dict) else {}
            value = _audio_annotation_value(labels)
            if value is None:
                continue
            records.append(_record_from_value(recording_id, username, value))
    records.sort(key=lambda record: (record["recording_id"], record["annotator"]))
    return records


def build_annotation_export_payload(
    records: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build the downloadable JSON document."""
    records = list(records)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recording_count": len({record["recording_id"] for record in records}),
        "annotation_count": len(records),
        "segment_count": sum(record["segment_count"] for record in records),
        "annotations": records,
    }


def write_annotation_sqlite(
    records: Iterable[Dict[str, Any]], path: Path
) -> None:
    """Write a standalone SQLite database containing annotation results."""
    with sqlite3.connect(str(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE annotations (
                id INTEGER PRIMARY KEY,
                recording_id TEXT NOT NULL,
                annotator TEXT NOT NULL,
                segment_count INTEGER NOT NULL,
                parse_error TEXT,
                review_status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by TEXT,
                reviewed_at TEXT
            );
            CREATE INDEX idx_annotations_recording
                ON annotations(recording_id);
            CREATE INDEX idx_annotations_annotator
                ON annotations(annotator);

            CREATE TABLE segments (
                id INTEGER PRIMARY KEY,
                annotation_id INTEGER NOT NULL,
                segment_id TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                speaker TEXT NOT NULL,
                text TEXT NOT NULL,
                is_dialect INTEGER NOT NULL,
                FOREIGN KEY(annotation_id) REFERENCES annotations(id)
            );
            CREATE INDEX idx_segments_annotation
                ON segments(annotation_id);
            """
        )
        for record in records:
            cursor = connection.execute(
                """
                INSERT INTO annotations
                    (recording_id, annotator, segment_count, parse_error,
                     review_status, reviewed_by, reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["recording_id"],
                    record["annotator"],
                    record["segment_count"],
                    record.get("parse_error"),
                    record.get("review_status", "pending"),
                    record.get("reviewed_by"),
                    record.get("reviewed_at"),
                ),
            )
            annotation_id = cursor.lastrowid
            connection.executemany(
                """
                INSERT INTO segments (
                    annotation_id, segment_id, start_time, end_time,
                    speaker, text, is_dialect
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        annotation_id,
                        segment["id"],
                        segment["start_time"],
                        segment["end_time"],
                        segment["speaker"],
                        segment["text"],
                        int(segment["is_dialect"]),
                    )
                    for segment in record["segments"]
                ],
            )
