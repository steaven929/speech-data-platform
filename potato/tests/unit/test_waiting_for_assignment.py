from unittest.mock import MagicMock

from flask import Flask

import potato.flask_server as flask_server
from potato.phase import UserPhase


def test_missing_current_item_renders_waiting_page_instead_of_redirect(monkeypatch):
    """An annotator with no valid assigned item must receive a stable page."""
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.add_url_rule("/", "home", lambda: "home")

    user_state = MagicMock()
    user_state.get_current_phase_and_page.return_value = (UserPhase.ANNOTATION, None)
    user_state.get_current_instance.return_value = None
    user_state.has_remaining_assignments.return_value = True

    user_state_manager = MagicMock()
    user_state_manager.get_user_state.return_value = user_state

    monkeypatch.setattr(flask_server, "get_user_state_manager", lambda: user_state_manager)
    monkeypatch.setattr(
        flask_server,
        "render_template",
        lambda template_name, **context: (template_name, context),
    )
    monkeypatch.setattr(
        flask_server,
        "config",
        {"annotation_task_name": "Phase Flow Test"},
        raising=False,
    )

    with app.test_request_context("/annotate"):
        response = flask_server.render_page_with_annotations("user14")

    assert response[0] == "waiting_for_assignment.html"
    assert response[1]["username"] == "user14"
    user_state_manager.advance_phase.assert_not_called()
