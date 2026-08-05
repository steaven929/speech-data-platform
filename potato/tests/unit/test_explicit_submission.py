import json

from potato.user_state_management import InMemoryUserState, Label, UserStateManager


def _draft_state() -> InMemoryUserState:
    state = InMemoryUserState("annotator")
    state.explicit_submission_required = True
    state.add_label_annotation("item-1", Label("transcript_segments", "_data"), '{"segments": [{}]}')
    return state


def test_draft_does_not_count_until_submitted():
    state = _draft_state()

    assert state.get_annotation_count() == 0
    assert not state.has_annotated("item-1")

    state.mark_submitted("item-1")

    assert state.get_annotation_count() == 1
    assert state.has_annotated("item-1")


def test_submission_round_trips_and_edits_remain_submitted(tmp_path):
    state = _draft_state()
    state.mark_submitted("item-1")
    state.save(str(tmp_path))

    loaded = InMemoryUserState.load(str(tmp_path))
    loaded.explicit_submission_required = True
    loaded.add_label_annotation("item-1", Label("transcript_segments", "_data"), '{"segments": [{"id": "edited"}]}')

    assert loaded.is_submitted("item-1")
    assert loaded.get_annotation_count() == 1


def test_old_state_without_submission_field_loads_as_unsubmitted(tmp_path):
    state = _draft_state()
    state.save(str(tmp_path))
    path = tmp_path / "user_state.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("submitted_instance_ids")
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = InMemoryUserState.load(str(tmp_path))
    loaded.explicit_submission_required = True

    assert loaded.get_submitted_instance_ids() == set()
    assert loaded.get_annotation_count() == 0


def test_manager_only_enables_explicit_mode_for_configured_task():
    explicit = UserStateManager({
        "annotation_submission": {"require_explicit_submit": True},
    }).add_user("explicit")
    legacy = UserStateManager({}).add_user("legacy")

    assert explicit.explicit_submission_required is True
    assert legacy.explicit_submission_required is False
