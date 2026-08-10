import json
import sqlite3

from potato.admin_annotation_data import (
    build_annotation_export_payload,
    collect_audio_annotation_records,
    write_annotation_sqlite,
)
from potato.item_state_management import Label


class FakeUserState:
    def __init__(self, annotations):
        self._annotations = annotations

    def get_all_annotations(self):
        return self._annotations


class FakeUserStateManager:
    def __init__(self, states):
        self._states = states

    def get_user_ids(self):
        return list(self._states)

    def get_user_state(self, username):
        return self._states[username]


def test_collects_only_saved_audio_annotations_and_sorts_segments():
    saved = json.dumps(
        {
            "segments": [
                {
                    "id": "second",
                    "start_time": 4.0,
                    "end_time": 6.0,
                    "label": "caller",
                    "text": "第二句",
                    "annotations": {"dialect": True},
                },
                {
                    "id": "first",
                    "start_time": 0.0,
                    "end_time": 3.0,
                    "label": "agent",
                    "text": "第一句",
                },
            ]
        },
        ensure_ascii=False,
    )
    manager = FakeUserStateManager(
        {
            "user2": FakeUserState(
                {
                    "recording-2": {
                        "labels": {
                            Label("transcript_segments", "_data"): saved,
                        },
                        "spans": {},
                    }
                }
            ),
            "empty_user": FakeUserState({}),
        }
    )

    records = collect_audio_annotation_records(manager)

    assert records == [
        {
            "recording_id": "recording-2",
            "annotator": "user2",
            "segment_count": 2,
            "segments": [
                {
                    "id": "first",
                    "start_time": 0.0,
                    "end_time": 3.0,
                    "speaker": "agent",
                    "text": "第一句",
                    "is_dialect": False,
                },
                {
                    "id": "second",
                    "start_time": 4.0,
                    "end_time": 6.0,
                    "speaker": "caller",
                    "text": "第二句",
                    "is_dialect": True,
                },
            ],
            "parse_error": None,
        }
    ]


def test_malformed_saved_audio_annotation_is_reported_without_crashing():
    manager = FakeUserStateManager(
        {
            "user2": FakeUserState(
                {
                    "broken-recording": {
                        "labels": {
                            "transcript_segments:::_data": "{not-json",
                        }
                    }
                }
            )
        }
    )

    records = collect_audio_annotation_records(manager)

    assert records[0]["recording_id"] == "broken-recording"
    assert records[0]["segment_count"] == 0
    assert records[0]["segments"] == []
    assert records[0]["parse_error"] == "标注数据格式错误"


def test_json_payload_and_sqlite_export_have_expected_counts_and_rows(tmp_path):
    records = [
        {
            "recording_id": "recording-1",
            "annotator": "user2",
            "segment_count": 1,
            "segments": [
                {
                    "id": "seg-1",
                    "start_time": 1.25,
                    "end_time": 2.5,
                    "speaker": "agent",
                    "text": "您好",
                    "is_dialect": False,
                }
            ],
            "parse_error": None,
            "review_status": "completed",
            "reviewed_by": "admin",
            "reviewed_at": "2026-08-03T01:00:00Z",
        }
    ]

    final_results = [{
        "recording_id": "recording-1",
        "annotator": "user2",
        "method": "three_way_medoid",
        "finalized_at": "2026-08-03T01:00:00Z",
        "annotation": {"segments": []},
        "comparisons": [{"annotators": ["user1", "user2"], "cer": 0.02}],
        "scores": {"user2": 0.05},
    }]
    payload = build_annotation_export_payload(records, final_results=final_results)
    assert payload["recording_count"] == 1
    assert payload["annotation_count"] == 1
    assert payload["segment_count"] == 1
    assert payload["annotations"] == records
    assert payload["final_results"] == final_results
    assert payload["exported_at"].endswith("Z")

    database_path = tmp_path / "annotations.sqlite"
    write_annotation_sqlite(records, database_path, final_results=final_results)
    with sqlite3.connect(database_path) as connection:
        annotation_row = connection.execute(
            "SELECT recording_id, annotator, segment_count, review_status, reviewed_by FROM annotations"
        ).fetchone()
        segment_row = connection.execute(
            """
            SELECT segment_id, start_time, end_time, speaker, text, is_dialect
            FROM segments
            """
        ).fetchone()
        final_row = connection.execute(
            "SELECT recording_id, annotator, method FROM final_results"
        ).fetchone()

    assert annotation_row == ("recording-1", "user2", 1, "completed", "admin")
    assert segment_row == ("seg-1", 1.25, 2.5, "agent", "您好", 0)
    assert final_row == ("recording-1", "user2", "three_way_medoid")
