from pathlib import Path

from flask import Flask

from potato import routes


def test_admin_key_form_post_establishes_session(monkeypatch):
    monkeypatch.setattr(routes, "validate_admin_api_key", lambda key: key == "valid-admin-key")
    monkeypatch.setattr(routes, "get_admin_api_key", lambda: "valid-admin-key")
    routes.app.config.update(TESTING=True, SECRET_KEY="admin-login-test")

    with routes.app.test_client() as client:
        response = client.post(
            "/admin",
            data={"apiKey": "valid-admin-key"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/admin")
        with client.session_transaction() as browser_session:
            assert browser_session["admin_api_key"] == "valid-admin-key"


def test_admin_login_template_uses_native_form_submission():
    template = Path(routes.__file__).parent / "templates" / "admin_login.html"
    content = template.read_text(encoding="utf-8")

    assert 'method="post"' in content
    assert 'action="{{ url_for(\'admin\') }}"' in content
    assert "fetch('/admin'" not in content


def test_configured_server_accepts_admin_form_post():
    original_app = routes.app
    original_config = routes.config
    served_app = Flask("admin-login-served-app")
    try:
        routes.configure_routes(served_app, {})
        admin_rule = next(rule for rule in served_app.url_map.iter_rules() if rule.rule == "/admin")
        assert "POST" in admin_rule.methods
    finally:
        routes.app = original_app
        routes.config = original_config
