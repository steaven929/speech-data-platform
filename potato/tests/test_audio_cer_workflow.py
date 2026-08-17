from potato.audio_cer_workflow import AudioCerWorkflowStore
from potato.routes import (
    _filter_completed_audio_reviews_by_final_method,
    _group_completed_audio_reviews,
    _group_manual_audio_reviews,
)


def _submit(store, recording_id, annotator, text, submitted_at):
    return store.note_submission(
        recording_id,
        annotator,
        text,
        {"segments": [{"text": text}]},
        submitted_at=submitted_at,
    )


def test_pair_cer_auto_finalizes(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec1", ["A", "B"])

    _submit(store, "rec1", "A", "hello world", "2026-08-12T00:00:00Z")
    _submit(store, "rec1", "B", "hello world", "2026-08-12T00:01:00Z")

    state = store.recalculate("rec1", pair_threshold=0.03, consensus_threshold=0.08)

    assert state["stage"] == "auto_finalized"
    assert state["final_method"] == "pair_cer"
    assert state["final_annotator"] == "A"


def test_pair_cer_waits_for_third_submission(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec1", ["A", "B"])
    store.set_third_annotator("rec1", "C")

    _submit(store, "rec1", "A", "aaaaaaaaaa", "2026-08-12T00:00:00Z")
    _submit(store, "rec1", "B", "bbbbbbbbbb", "2026-08-12T00:01:00Z")

    state = store.recalculate("rec1", pair_threshold=0.03, consensus_threshold=0.08)

    assert state["stage"] == "awaiting_third_submission"


def test_three_way_min_cer_under_threshold_auto_finalizes_medoid(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec1", ["A", "B"])
    store.set_third_annotator("rec1", "C")

    _submit(store, "rec1", "A", "aaaaaaaaaaaaaaaaaaaaaaaaa", "2026-08-12T00:00:00Z")
    _submit(store, "rec1", "B", "aaaaaaaaaaaaaaaaaaaaaaaab", "2026-08-12T00:01:00Z")
    _submit(store, "rec1", "C", "bbbbbbbbbbbbbbbbbbbbbbbbb", "2026-08-12T00:02:00Z")

    state = store.recalculate("rec1", pair_threshold=0.03, consensus_threshold=0.08)

    assert min(row["cer"] for row in state["comparisons"]) < 0.08
    assert state["stage"] == "auto_finalized"
    assert state["final_method"] == "three_way_medoid"
    assert state["final_annotator"] == min(state["scores"], key=state["scores"].get)
    assert state["review_candidate"] == state["final_annotator"]


def test_three_way_all_cer_at_or_above_threshold_needs_manual_review(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec1", ["A", "B"])
    store.set_third_annotator("rec1", "C")

    _submit(store, "rec1", "A", "aaaaaaaaaa", "2026-08-12T00:00:00Z")
    _submit(store, "rec1", "B", "bbbbbbbbbb", "2026-08-12T00:01:00Z")
    _submit(store, "rec1", "C", "cccccccccc", "2026-08-12T00:02:00Z")

    state = store.recalculate("rec1", pair_threshold=0.03, consensus_threshold=0.08)

    assert min(row["cer"] for row in state["comparisons"]) > 0.08
    assert state["stage"] == "needs_manual_review"
    assert state["review_candidate"] == min(state["scores"], key=state["scores"].get)
    assert state["final_annotator"] is None


def test_three_way_min_cer_equal_threshold_needs_manual_review(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec1", ["A", "B"])
    store.set_third_annotator("rec1", "C")

    _submit(store, "rec1", "A", "aaaaaaaaaaaaaaaaaaaaaaaaa", "2026-08-12T00:00:00Z")
    _submit(store, "rec1", "B", "aaaaaaaaaaaaaaaaaaaaaaabb", "2026-08-12T00:01:00Z")
    _submit(store, "rec1", "C", "bbbbbbbbbbbbbbbbbbbbbbbbb", "2026-08-12T00:02:00Z")

    state = store.recalculate("rec1", pair_threshold=0.03, consensus_threshold=0.08)

    assert min(row["cer"] for row in state["comparisons"]) == 0.08
    assert state["stage"] == "needs_manual_review"
    assert state["review_candidate"] == min(state["scores"], key=state["scores"].get)


def test_three_way_tie_breaker_uses_earlier_submission(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec1", ["B", "A"])
    store.set_third_annotator("rec1", "C")

    _submit(store, "rec1", "B", "aaaaaaaaaa", "2026-08-12T00:02:00Z")
    _submit(store, "rec1", "A", "bbbbbbbbbb", "2026-08-12T00:00:00Z")
    _submit(store, "rec1", "C", "cccccccccc", "2026-08-12T00:01:00Z")

    state = store.recalculate("rec1", pair_threshold=0.03, consensus_threshold=0.08)

    assert state["stage"] == "needs_manual_review"
    assert state["review_candidate"] == "A"
    assert state["tie_breaker"] == "earlier_submission"


def test_manual_finalized_record_is_not_reopened_by_later_annotator_submission(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec1", ["A", "B"])
    store.set_third_annotator("rec1", "C")

    _submit(store, "rec1", "A", "aaaaaaaaaa", "2026-08-12T00:00:00Z")
    _submit(store, "rec1", "B", "bbbbbbbbbb", "2026-08-12T00:01:00Z")
    _submit(store, "rec1", "C", "cccccccccc", "2026-08-12T00:02:00Z")
    state = store.recalculate("rec1", pair_threshold=0.03, consensus_threshold=0.08)
    assert state["stage"] == "needs_manual_review"

    original_final = {"segments": [{"text": "admin final text"}]}
    finalized = store.finalize_manual("rec1", "A", original_final, "admin")
    assert finalized["stage"] == "manual_finalized"

    _submit(store, "rec1", "A", "changed later by annotator", "2026-08-12T00:03:00Z")
    recalculated = store.recalculate("rec1", pair_threshold=0.03, consensus_threshold=0.08)

    assert recalculated["stage"] == "manual_finalized"
    assert recalculated["final_annotator"] == "A"
    assert recalculated["final_method"] == "manual"
    assert recalculated["final_annotation"] == original_final


def test_adjudication_in_progress_only_contains_manual_review_stage():
    records = [
        {"recording_id": "initial", "annotator": "A", "workflow_stage": "awaiting_pair_submissions", "review_status": "in_progress"},
        {"recording_id": "third", "annotator": "C", "workflow_stage": "awaiting_third_submission", "review_status": "in_progress"},
        {"recording_id": "manual", "annotator": "A", "workflow_stage": "needs_manual_review", "review_status": "in_progress"},
    ]

    filtered = [row for row in records if row.get("workflow_stage") == "needs_manual_review"]
    grouped = _group_manual_audio_reviews(filtered)

    assert [row["recording_id"] for row in grouped] == ["manual"]


def test_completed_audio_review_filter_applies_to_grouped_final_method():
    records = [
        {
            "recording_id": "pair", "annotator": "A",
            "review_status": "completed", "final_annotator": "A",
            "final_method": "pair_cer", "is_final_result": True,
            "workflow_comparisons": [],
        },
        {
            "recording_id": "pair", "annotator": "B",
            "review_status": "completed", "final_annotator": "A",
            "final_method": "pair_cer", "is_final_result": False,
            "workflow_comparisons": [],
        },
        {
            "recording_id": "three", "annotator": "A",
            "review_status": "completed", "final_annotator": "B",
            "final_method": "three_way_medoid", "is_final_result": False,
            "workflow_comparisons": [],
        },
        {
            "recording_id": "three", "annotator": "B",
            "review_status": "completed", "final_annotator": "B",
            "final_method": "three_way_medoid", "is_final_result": True,
            "workflow_comparisons": [],
        },
        {
            "recording_id": "manual", "annotator": "A",
            "review_status": "completed", "final_annotator": "A",
            "final_method": "manual", "is_final_result": True,
            "workflow_comparisons": [],
        },
    ]

    recordings = _group_completed_audio_reviews(records)
    unchanged_records, filtered = _filter_completed_audio_reviews_by_final_method(
        records, recordings, True, "three_way_medoid"
    )
    _, all_recordings = _filter_completed_audio_reviews_by_final_method(
        records, recordings, True, ""
    )

    assert unchanged_records is records
    assert [row["recording_id"] for row in filtered] == ["three"]
    assert sorted(row["recording_id"] for row in all_recordings) == [
        "manual",
        "pair",
        "three",
    ]
