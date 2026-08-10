from potato.audio_cer_workflow import AudioCerWorkflowStore
from potato.item_state_management import ItemStateManager
from potato.user_state_management import InMemoryUserState


def _payload(text):
    return {"segments": [{
        "id": "s1", "start_time": 0, "end_time": 1, "text": text,
    }]}


def _submit(store, user, text, timestamp):
    store.note_submission("rec", user, text, _payload(text), timestamp)


def test_pair_at_three_percent_is_auto_finalized(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    _submit(store, "a", "x" * 100, "2026-01-01T00:00:00Z")
    _submit(store, "b", "x" * 97 + "yyy", "2026-01-01T00:00:01Z")

    state = store.recalculate("rec")

    assert state["stage"] == "auto_finalized"
    assert state["comparisons"][0]["cer"] == 0.03
    assert state["final_annotator"] == "a"
    assert state["final_method"] == "pair_cer"


def test_pair_over_three_percent_waits_for_third(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    _submit(store, "a", "abcdefghij", "2026-01-01T00:00:00Z")
    _submit(store, "b", "abcdefghiX", "2026-01-01T00:00:01Z")

    state = store.recalculate("rec")

    assert state["stage"] == "waiting_third_assignment"
    assert state["comparisons"][0]["cer"] == 0.1


def test_three_way_medoid_uses_total_distance(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    store.set_third_annotator("rec", "c")
    _submit(store, "a", "x" * 100, "2026-01-01T00:00:00Z")
    _submit(store, "b", "x" * 91 + "y" * 9, "2026-01-01T00:00:01Z")
    _submit(store, "c", "x" * 98 + "zz", "2026-01-01T00:00:02Z")

    state = store.recalculate("rec")

    assert state["stage"] == "auto_finalized"
    assert state["final_annotator"] == "a"
    assert state["final_method"] == "three_way_medoid"
    assert state["scores"]["a"] < state["scores"]["b"]


def test_three_way_medoid_tie_prefers_earlier_submission(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    store.set_third_annotator("rec", "c")
    _submit(store, "a", "abcdefghij", "2026-01-01T00:00:02Z")
    _submit(store, "b", "abcdefghiX", "2026-01-01T00:00:01Z")
    _submit(store, "c", "abcdefghYZ", "2026-01-01T00:00:03Z")

    state = store.recalculate("rec", consensus_threshold=0.2)

    assert state["stage"] == "auto_finalized"
    assert state["scores"]["a"] == state["scores"]["b"]
    assert state["final_annotator"] == "b"


def test_all_three_over_eight_percent_require_manual_review(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    store.set_third_annotator("rec", "c")
    _submit(store, "a", "aaaaaaaaaa", "2026-01-01T00:00:00Z")
    _submit(store, "b", "bbbbbbbbbb", "2026-01-01T00:00:01Z")
    _submit(store, "c", "cccccccccc", "2026-01-01T00:00:02Z")

    state = store.recalculate("rec")

    assert state["stage"] == "needs_manual_review"
    finalized = store.finalize_manual("rec", "b", _payload("bbbbbbbbbb"), "admin")
    assert finalized["stage"] == "manual_finalized"
    assert finalized["final_annotator"] == "b"
    reopened = store.reopen_for_manual_review("rec", "admin")
    assert reopened["stage"] == "needs_manual_review"


def test_blank_transcription_never_auto_passes(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    _submit(store, "a", "  ，。", "2026-01-01T00:00:00Z")
    _submit(store, "b", "", "2026-01-01T00:00:01Z")

    state = store.recalculate("rec")

    assert state["stage"] == "needs_manual_review"
    assert "空白" in state["reason"]


def test_more_than_three_legacy_submissions_require_manual_review(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    for index, user in enumerate("abcd"):
        _submit(store, user, user * 10, f"2026-01-01T00:00:0{index}Z")

    state = store.recalculate("rec", history_reason="workflow_v2_migration")

    assert state["stage"] == "needs_manual_review"
    assert state["history"][-1]["reason"] == "workflow_v2_migration"


def test_cer_first_round_is_not_assigned_on_annotator_login():
    manager = ItemStateManager({
        "assignment_strategy": "least_annotated",
        "num_annotators_per_item": 2,
        "annotation_submission": {"cer_review": {
            "enabled": True, "initial_assignment": "admin_batch",
        }},
    })
    manager.add_items({"rec": {"id": "rec", "text": "audio"}})
    worker = InMemoryUserState("worker")

    assigned = manager.assign_instances_to_user(worker)
    report = manager.fill_assignments_to_coverage([worker])

    assert assigned == 0
    assert worker.get_assigned_instance_count() == 0
    assert report["admin_managed"] is True
