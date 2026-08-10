from potato import routes
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
