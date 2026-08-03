import json

import pytest

from potato.direct_audio_review import DirectAudioReviewStore, ReviewConflict


def test_claim_is_exclusive_and_persists_after_reload(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    claimed = store.claim("rec-1", "user2", "admin")
    assert claimed["status"] == "in_progress"
    assert claimed["assigned_to"] == "admin"

    reloaded = DirectAudioReviewStore(tmp_path)
    review = reloaded.get("rec-1", "user2")
    assert review["status"] == "in_progress"
    assert review["assigned_to"] == "admin"

    with pytest.raises(ReviewConflict):
        reloaded.claim("rec-1", "user2", "other_admin")


def test_complete_and_reopen_require_the_claim_owner(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    store.claim("rec-1", "user2", "admin")
    completed = store.complete("rec-1", "user2", "admin")
    assert completed["status"] == "completed"
    assert completed["reviewed_by"] == "admin"
    assert completed["reviewed_at"]

    reopened = store.reopen("rec-1", "user2", "admin")
    assert reopened["status"] == "in_progress"
    assert reopened["reviewed_at"] is None


def test_snapshot_is_append_only_and_contains_old_value(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    first = store.record_snapshot("rec-1", "user2", "admin", "old-one")
    second = store.record_snapshot("rec-1", "user2", "admin", "old-two")
    assert first["snapshot_id"] != second["snapshot_id"]

    history_files = sorted((tmp_path / "admin_review" / "history").glob("*.json"))
    assert len(history_files) == 2
    values = [json.loads(path.read_text())["old_value"] for path in history_files]
    assert values == ["old-one", "old-two"]


def test_list_reviews_adds_pending_state_to_new_saved_records(tmp_path):
    store = DirectAudioReviewStore(tmp_path)
    records = [{"recording_id": "rec-1", "annotator": "user2"}]
    listed = store.list_reviews(records)
    assert listed[0]["review_status"] == "pending"
    assert listed[0]["assigned_to"] is None
