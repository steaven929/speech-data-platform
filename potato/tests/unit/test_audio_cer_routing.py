import pytest

from potato import routes
from potato import admin_annotation_data
from potato.item_state_management import ItemStateManager
from potato.user_state_management import InMemoryUserState


class _State:
    def __init__(self, assigned=(), annotated=(), maximum=-1):
        self.assigned = set(assigned)
        self.annotated = set(annotated)
        self.maximum = maximum

    def has_annotated(self, item_id):
        return item_id in self.annotated

    def get_assigned_instance_ids(self):
        return set(self.assigned)

    def get_max_assignments(self):
        return self.maximum


class _Users:
    def __init__(self, states):
        self.states = states

    def get_user_ids(self):
        return self.states.keys()

    def get_user_state(self, username):
        return self.states[username]

    def get_all_users(self):
        return list(self.states.values())

    def save_user_state(self, _state):
        return None


class _Items:
    def get_instance_ids(self):
        return ["rec", "other"]


def test_third_candidate_excludes_prior_users_roles_completed_and_full(monkeypatch):
    users = _Users({
        "a": _State(),
        "admin": _State(),
        "reviewer": _State(),
        "already": _State(annotated={"rec"}),
        "full": _State(assigned={"other"}, maximum=1),
        "eligible": _State(assigned={"other"}, maximum=2),
    })
    monkeypatch.setattr(routes, "get_user_state_manager", lambda: users)
    monkeypatch.setattr(routes, "get_item_state_manager", lambda: _Items())
    monkeypatch.setitem(routes.config, "rbac", {"user_role_assignments": {
        "admin": "admin", "reviewer": "adjudicator",
    }})
    monkeypatch.setitem(routes.config, "adjudication", {
        "adjudicator_users": ["reviewer"],
    })

    candidates = routes._eligible_third_annotators("rec", {"a"})

    assert candidates == ["eligible"]


def _batch_context(monkeypatch):
    manager = ItemStateManager({
        "assignment_strategy": "least_annotated",
        "num_annotators_per_item": 2,
    })
    manager.add_items({"rec": {"id": "rec", "text": "audio"}})
    states = {}
    for username in ("a", "b", "c"):
        state = InMemoryUserState(username)
        state.set_max_assignments(10)
        states[username] = state
    users = _Users(states)
    monkeypatch.setattr(routes, "get_item_state_manager", lambda: manager)
    monkeypatch.setattr(routes, "get_user_state_manager", lambda: users)
    monkeypatch.setitem(routes.config, "annotation_submission", {
        "cer_review": {"enabled": True},
    })
    return manager, users


def test_batch_preview_forces_two_person_target(monkeypatch):
    _batch_context(monkeypatch)
    with routes.app.test_request_context(json={
        "item_ids": ["rec"],
        "annotator_ids": ["a", "b", "c"],
        "target_per_item": 3,
        "dry_run": True,
    }):
        response = routes.admin_api_batch_assignment.__wrapped__()

    data = response.get_json()
    assert data["target_per_item"] == 2
    assert len(data["plan"][0]["suggested"]) == 2


def test_batch_confirm_rejects_partial_first_round(monkeypatch):
    _batch_context(monkeypatch)
    with routes.app.test_request_context(json={
        "item_ids": ["rec"],
        "annotator_ids": ["a", "b"],
        "dry_run": False,
        "plan": [{"item_id": "rec", "suggested": ["a"]}],
    }):
        response, status = routes.admin_api_batch_assignment.__wrapped__()

    assert status == 400
    assert "恰好分配两人" in response.get_json()["details"][0]


@pytest.mark.parametrize("final_annotator", ["a", "b", "c"])
@pytest.mark.parametrize("final_method", ["pair_cer", "three_way_medoid", "manual"])
def test_completed_review_api_groups_three_results_by_recording(
    monkeypatch, final_annotator, final_method
):
    rows = [
        {
            "recording_id": "rec",
            "annotator": annotator,
            "review_status": "completed",
            "segments": [{"id": annotator, "text": annotator}],
            "segment_count": 1,
            "is_final_result": annotator == final_annotator,
            "final_annotator": final_annotator,
            "final_method": final_method,
            "finalized_at": "2026-08-10T12:00:00Z",
            "workflow_comparisons": [
                {"annotators": ["a", "b"], "cer": 0.05},
                {"annotators": ["a", "c"], "cer": 0.10},
                {"annotators": ["b", "c"], "cer": 0.05},
            ],
            "workflow_scores": {"a": 0.15, "b": 0.10, "c": 0.15},
            "selection_reason": f"标注员 {final_annotator} 的总差异最小，因此系统选择 {final_annotator} 作为最终结果",
            "tie_breaker": None,
        }
        for annotator in ("a", "b", "c")
    ]
    monkeypatch.setattr(routes, "_check_adjudicator_auth", lambda: (True, "admin", None))
    monkeypatch.setattr(routes, "_cer_review_config", lambda: {"enabled": True})
    monkeypatch.setattr(
        admin_annotation_data,
        "collect_audio_annotation_records",
        lambda _manager: [{"recording_id": "rec"}],
    )
    monkeypatch.setattr(routes, "get_user_state_manager", lambda: object())
    monkeypatch.setattr(routes, "_decorate_audio_review_records", lambda _records: rows)

    with routes.app.test_request_context(
        "/adjudicate/api/audio-reviews?status=completed"
    ):
        response = routes.direct_audio_review_queue()

    payload = response.get_json()
    assert payload["total"] == 3
    assert payload["recording_total"] == 1
    assert len(payload["recordings"]) == 1
    group = payload["recordings"][0]
    assert group["recording_id"] == "rec"
    assert group["final_status"] == "ready"
    assert group["final_result"]["annotator"] == final_annotator
    assert group["final_method"] == final_method
    assert [row["annotator"] for row in group["original_results"]] == [
        annotator for annotator in ("a", "b", "c")
        if annotator != final_annotator
    ]
    assert group["minimum_cer"] == 0.05


def test_completed_review_api_does_not_guess_when_final_result_is_missing(monkeypatch):
    rows = [
        {
            "recording_id": "rec",
            "annotator": annotator,
            "review_status": "completed",
            "is_final_result": False,
            "final_annotator": "missing-user",
            "workflow_comparisons": [],
        }
        for annotator in ("a", "b", "c")
    ]
    monkeypatch.setattr(routes, "_check_adjudicator_auth", lambda: (True, "admin", None))
    monkeypatch.setattr(routes, "_cer_review_config", lambda: {"enabled": True})
    monkeypatch.setattr(
        admin_annotation_data,
        "collect_audio_annotation_records",
        lambda _manager: [{"recording_id": "rec"}],
    )
    monkeypatch.setattr(routes, "get_user_state_manager", lambda: object())
    monkeypatch.setattr(routes, "_decorate_audio_review_records", lambda _records: rows)

    with routes.app.test_request_context(
        "/adjudicate/api/audio-reviews?status=completed"
    ):
        response = routes.direct_audio_review_queue()

    group = response.get_json()["recordings"][0]
    assert group["final_status"] == "error"
    assert group["final_error"] == "最终稿数据异常"
    assert group["final_result"] is None
    assert [row["annotator"] for row in group["original_results"]] == ["a", "b", "c"]
