import json

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
    assert state["tie_breaker"] == "earlier_submission"
    assert state["selection_reason"] == "双人 CER 3.00% 达标"
    assert "提交时间更早" not in state["selection_reason"]


def test_existing_pair_result_hides_old_submission_time_explanation(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    _submit(store, "a", "x" * 100, "2026-01-01T00:00:00Z")
    _submit(store, "b", "x" * 97 + "yyy", "2026-01-01T00:00:01Z")
    store.recalculate("rec")
    store._data["recordings"]["rec"]["selection_reason"] = (
        "双人 CER 3.00% 达标；标注员 a 提交时间更早，因此作为最终结果"
    )

    decorated = store.decorate_records([
        {"recording_id": "rec", "annotator": "a"}
    ])[0]

    assert decorated["selection_reason"] == "双人 CER 3.00% 达标"
    assert decorated["tie_breaker"] == "earlier_submission"


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
    _submit(store, "b", "x" * 95 + "y" * 5, "2026-01-01T00:00:01Z")
    _submit(store, "c", "x" * 90 + "y" * 10, "2026-01-01T00:00:02Z")

    state = store.recalculate("rec")

    assert state["stage"] == "auto_finalized"
    assert state["final_annotator"] == "b"
    assert state["final_method"] == "three_way_medoid"
    assert state["scores"]["b"] < state["scores"]["a"]
    assert state["scores"]["b"] < state["scores"]["c"]
    assert state["selection_reason"] == "标注员 b 的总差异最小，因此系统选择 b 作为最终结果"
    assert state["tie_breaker"] is None


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
    assert state["tie_breaker"] == "earlier_submission"
    assert "提交时间更早" in state["selection_reason"]


def test_three_way_medoid_tie_without_timestamps_uses_annotator_id(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    store.set_third_annotator("rec", "c")
    store.note_submission("rec", "b", "abcdefghiX", _payload("abcdefghiX"))
    store.note_submission("rec", "a", "abcdefghij", _payload("abcdefghij"))
    store.note_submission("rec", "c", "abcdefghYZ", _payload("abcdefghYZ"))
    for row in store._data["recordings"]["rec"]["submissions"].values():
        row["submitted_at"] = None

    state = store.recalculate("rec", consensus_threshold=0.2)

    assert state["scores"]["a"] == state["scores"]["b"]
    assert state["final_annotator"] == "a"
    assert state["tie_breaker"] == "annotator_id"
    assert "标注员编号" in state["selection_reason"]


def test_legacy_finalized_state_derives_missing_selection_explanation(tmp_path):
    store = AudioCerWorkflowStore(tmp_path)
    store.register_initial_assignments("rec", ["a", "b"])
    store.set_third_annotator("rec", "c")
    _submit(store, "a", "x" * 100, "2026-01-01T00:00:00Z")
    _submit(store, "b", "x" * 95 + "y" * 5, "2026-01-01T00:00:01Z")
    _submit(store, "c", "x" * 90 + "y" * 10, "2026-01-01T00:00:02Z")
    store.recalculate("rec")
    state_path = tmp_path / "admin_review" / "cer_workflow_state.json"
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    persisted["recordings"]["rec"].pop("selection_reason")
    persisted["recordings"]["rec"].pop("tie_breaker")
    state_path.write_text(json.dumps(persisted), encoding="utf-8")

    legacy_store = AudioCerWorkflowStore(tmp_path)
    decorated = legacy_store.decorate_records([
        {"recording_id": "rec", "annotator": "b"}
    ])[0]

    assert decorated["selection_reason"] == (
        "标注员 b 的总差异最小，因此系统选择 b 作为最终结果"
    )
    assert decorated["tie_breaker"] is None


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
