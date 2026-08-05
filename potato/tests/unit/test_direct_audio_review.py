import json

from potato.direct_audio_review import DirectAudioReviewStore


def test_new_reviews_start_in_progress_without_an_owner(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    review = store.get("rec-1", "user2")
    assert review["status"] == "in_progress"
    assert review["assigned_to"] is None


def test_any_admin_can_complete_and_reopen(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    completed = store.complete("rec-1", "user2", "admin")
    assert completed["status"] == "completed"
    assert completed["reviewed_by"] == "admin"
    assert completed["reviewed_at"]

    reopened = store.reopen("rec-1", "user2", "other_admin")
    assert reopened["status"] == "in_progress"
    assert reopened["reviewed_at"] is None
    assert reopened["reopened_by"] == "other_admin"
    assert reopened["reopened_at"]


def test_old_pending_state_is_normalised_on_load(tmp_path):
    state_dir = tmp_path / "admin_review"
    state_dir.mkdir()
    (state_dir / "review_state.json").write_text(json.dumps({
        "rec-1::user2": {
            "status": "pending", "assigned_to": None, "assigned_at": None,
            "reviewed_by": None, "reviewed_at": None,
        }
    }), encoding="utf-8")

    store = DirectAudioReviewStore(tmp_path)
    assert store.get("rec-1", "user2")["status"] == "in_progress"


def test_snapshot_is_append_only_and_contains_old_value(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    first = store.record_snapshot("rec-1", "user2", "admin", "old-one")
    second = store.record_snapshot("rec-1", "user2", "admin", "old-two")
    assert first["snapshot_id"] != second["snapshot_id"]

    history_files = sorted((tmp_path / "admin_review" / "history").glob("*.json"))
    assert len(history_files) == 2
    values = [json.loads(path.read_text())["old_value"] for path in history_files]
    assert set(values) == {"old-one", "old-two"}


def test_list_reviews_adds_in_progress_state_to_new_saved_records(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    records = [{"recording_id": "rec-1", "annotator": "user2"}]
    listed = store.list_reviews(records)
    assert listed[0]["review_status"] == "in_progress"
    assert listed[0]["assigned_to"] is None


def test_auto_rejection_is_audited_and_auto_match_completes_only_group(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    rejected = store.record_auto_rejection("rec-1", "bad", "一字未改")
    assert rejected["status"] == "in_progress"
    assert rejected["review_method"] == "system_rejected"
    assert rejected["reject_count"] == 1

    comparisons = [
        {"annotators": ["a", "b"], "cer": 0.02, "passed": True},
        {"annotators": ["a", "c"], "cer": 0.4, "passed": False},
    ]
    completed = store.reconcile_auto_matches("rec-1", ["a", "b"], comparisons, 0.05)
    assert completed == ["a", "b"]
    assert store.get("rec-1", "a")["reviewed_by"] == "system:cer"
    assert store.get("rec-1", "a")["cer_score"] == 0.02
    assert store.get("rec-1", "c")["status"] == "in_progress"
