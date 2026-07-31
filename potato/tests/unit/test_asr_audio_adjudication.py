import json

from potato.adjudication import (
    AdjudicationDecision,
    AdjudicationItem,
    AdjudicationManager,
)


def make_manager(tmp_path):
    manager = AdjudicationManager(
        {
            "output_annotation_dir": str(tmp_path / "annotation_output"),
            "annotation_schemes": [
                {
                    "annotation_type": "audio_annotation",
                    "name": "transcript_segments",
                }
            ],
            "adjudication": {
                "enabled": True,
                "adjudicator_users": ["admin"],
                "show_all_items": True,
            },
        }
    )
    return manager


def test_audio_adoption_is_saved_as_complete_segments(tmp_path):
    manager = make_manager(tmp_path)
    user2_segments = [
        {
            "id": "segment_1",
            "start_time": 0.0,
            "end_time": 1.2,
            "label": "caller",
            "text": "你好",
            "annotations": {},
        },
        {
            "id": "segment_2",
            "start_time": 1.3,
            "end_time": 2.5,
            "label": "agent",
            "text": "您好",
            "annotations": {},
        },
    ]
    tester_segments = [
        {
            "id": "segment_1",
            "start_time": 0.0,
            "end_time": 1.1,
            "label": "caller",
            "text": "你好",
            "annotations": {},
        }
    ]
    manager.queue["recording_1"] = AdjudicationItem(
        instance_id="recording_1",
        annotations={
            "user2": {
                "transcript_segments": json.dumps(
                    {"segments": user2_segments}, ensure_ascii=False
                )
            },
            "tester_a": {
                "transcript_segments": json.dumps(
                    {"segments": tester_segments}, ensure_ascii=False
                )
            },
        },
        span_annotations={},
        behavioral_data={},
        agreement_scores={"transcript_segments": 0.0},
        overall_agreement=0.0,
        num_annotators=2,
    )
    decision = AdjudicationDecision(
        instance_id="recording_1",
        adjudicator_id="admin",
        timestamp="2026-07-31T00:00:00",
        label_decisions={
            "transcript_segments": {
                "adopted_annotations": [
                    {"annotator": "user2", "idx": "0", "type": "audio"},
                    {"annotator": "user2", "idx": "1", "type": "audio"},
                ]
            }
        },
        span_decisions=[],
        source={"transcript_segments": "adjudicator"},
        confidence="high",
        notes="full review",
        error_taxonomy=[],
    )

    assert manager.submit_decision(decision) is True

    saved = manager.get_decision("recording_1")
    assert saved.label_decisions["transcript_segments"] == {
        "segments": user2_segments
    }
    decisions_file = (
        tmp_path / "annotation_output" / "adjudication" / "decisions.json"
    )
    persisted = json.loads(decisions_file.read_text(encoding="utf-8"))
    assert persisted["decisions"][0]["label_decisions"]["transcript_segments"] == {
        "segments": user2_segments
    }
