from types import SimpleNamespace

from potato.adjudication import AdjudicationDecision, AdjudicationManager


class FakeItem:
    def __init__(self, data):
        self._data = data

    def get_data(self):
        return self._data


def test_final_export_preserves_reviewed_audio_segments(tmp_path, monkeypatch):
    segments = [
        {
            "id": "segment_1",
            "start_time": 0.0,
            "end_time": 1.2,
            "label": "caller",
            "text": "你好",
            "annotations": {},
        }
    ]
    manager = AdjudicationManager(
        {
            "output_annotation_dir": str(tmp_path),
            "annotation_schemes": [
                {
                    "annotation_type": "audio_annotation",
                    "name": "transcript_segments",
                }
            ],
            "adjudication": {
                "enabled": True,
                "adjudicator_users": ["admin"],
            },
        }
    )
    manager.decisions["recording_1"] = AdjudicationDecision(
        instance_id="recording_1",
        adjudicator_id="admin",
        timestamp="2026-07-31T00:00:00",
        label_decisions={"transcript_segments": {"segments": segments}},
        span_decisions=[],
        source={"transcript_segments": "adjudicator"},
        confidence="high",
        notes="",
        error_taxonomy=[],
    )
    item_manager = SimpleNamespace(
        instance_id_to_instance={
            "recording_1": FakeItem({"id": "recording_1", "audio": "one.wav"}),
            "recording_2": FakeItem({"id": "recording_2", "audio": "two.wav"}),
        },
        instance_annotators={
            "recording_1": {"user2", "annotator_a"},
            "recording_2": {"user2"},
        },
    )
    monkeypatch.setattr(
        "potato.item_state_management.get_item_state_manager",
        lambda: item_manager,
    )
    monkeypatch.setattr(
        "potato.user_state_management.get_user_state_manager",
        lambda: SimpleNamespace(),
    )

    rows = manager.generate_final_dataset()
    final_rows = [row for row in rows if row["source"] != "unresolved"]

    assert len(final_rows) == 1
    assert final_rows[0]["instance_id"] == "recording_1"
    assert final_rows[0]["source"] == "adjudicated"
    assert final_rows[0]["labels"]["transcript_segments"] == {
        "segments": segments
    }
    assert all(row["source"] != "unresolved" for row in final_rows)
