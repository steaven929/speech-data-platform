import io
import wave

import pytest


def wav_bytes(seconds=1, rate=8000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * seconds * rate)
    buffer.seek(0)
    return buffer


@pytest.fixture
def admin_client(monkeypatch, tmp_path):
    import potato.routes as routes

    routes.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    monkeypatch.setitem(routes.config, "admin_api_key", "audio-import-key")
    monkeypatch.setitem(routes.config, "task_dir", str(tmp_path))
    monkeypatch.setitem(routes.config, "media_directory", "media")
    monkeypatch.setitem(routes.config, "data_files", ["data/items.json"])
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "items.json").write_text("[]", encoding="utf-8")
    return routes.app.test_client()


def test_audio_import_preview_requires_admin(admin_client):
    response = admin_client.post("/admin/api/audio-import/preview")
    assert response.status_code == 403


def test_audio_import_preview_returns_token_and_validation_summary(
    admin_client, monkeypatch
):
    from potato.admin_audio_import import TranscriptRow
    import potato.admin_audio_import as audio_import

    monkeypatch.setattr(
        audio_import,
        "parse_legacy_xls",
        lambda path: [TranscriptRow("10001", "10001.wav", "客服。\n\n来电人。")],
    )
    response = admin_client.post(
        "/admin/api/audio-import/preview",
        headers={"X-API-Key": "audio-import-key"},
        data={
            "excel": (io.BytesIO(b"legacy-xls"), "transcript.xls"),
            "audio": (wav_bytes(), "10001.wav"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["preview"]["ready"] == ["10001"]
    assert payload["preview"]["can_confirm"] is True
    assert payload["token"]


def test_audio_import_preview_accepts_unified_manifest_field(
    admin_client, monkeypatch
):
    from potato.admin_audio_import import TranscriptRow
    import potato.admin_audio_import as audio_import

    monkeypatch.setattr(
        audio_import,
        "parse_legacy_xls",
        lambda path: [TranscriptRow("10001", "10001.wav", "客服。\n\n来电人。")],
    )
    response = admin_client.post(
        "/admin/api/audio-import/preview",
        headers={"X-API-Key": "audio-import-key"},
        data={
            "manifest": (io.BytesIO(b"legacy-xls"), "transcript.xls"),
            "audio": (wav_bytes(), "10001.wav"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["preview"]["ready"] == ["10001"]
    assert payload["preview"]["can_confirm"] is True


def test_audio_import_confirm_persists_and_consumes_token(admin_client, monkeypatch):
    from potato.admin_audio_import import TranscriptRow
    import potato.admin_audio_import as audio_import
    import potato.routes as routes

    monkeypatch.setattr(
        audio_import,
        "parse_legacy_xls",
        lambda path: [TranscriptRow("10001", "10001.wav", "客服。\n\n来电人。")],
    )

    class Manager:
        def __init__(self):
            self.coverage_calls = 0

        def get_instance_ids(self):
            return []

        def add_item(self, item_id, item):
            pass

        def fill_assignments_to_coverage(self, users):
            self.coverage_calls += 1
            return {"new_assignments": 0, "total_shortfall": 0}

    manager = Manager()
    monkeypatch.setattr(routes, "get_item_state_manager", lambda: manager)
    preview = admin_client.post(
        "/admin/api/audio-import/preview",
        headers={"X-API-Key": "audio-import-key"},
        data={
            "excel": (io.BytesIO(b"legacy-xls"), "transcript.xls"),
            "audio": (wav_bytes(), "10001.wav"),
        },
        content_type="multipart/form-data",
    ).get_json()

    response = admin_client.post(
        "/admin/api/audio-import/confirm",
        headers={"X-API-Key": "audio-import-key"},
        json={"token": preview["token"]},
    )

    assert response.status_code == 200
    assert response.get_json()["imported_ids"] == ["10001"]
    # 导入后不再自动分配，由管理员在分配界面手动下发
    assert manager.coverage_calls == 0
    repeated = admin_client.post(
        "/admin/api/audio-import/confirm",
        headers={"X-API-Key": "audio-import-key"},
        json={"token": preview["token"]},
    )
    assert repeated.status_code == 404


def test_configure_routes_registers_audio_import_endpoints_for_cli_server():
    from flask import Flask
    import potato.routes as routes

    original_app = routes.app
    original_config = routes.config
    cli_app = Flask("audio-import-cli-registration")
    try:
        routes.configure_routes(cli_app, {})
        rules = {
            rule.rule: rule.methods
            for rule in cli_app.url_map.iter_rules()
        }
    finally:
        routes.app = original_app
        routes.config = original_config

    assert "POST" in rules["/admin/api/audio-import/preview"]
    assert "POST" in rules["/admin/api/audio-import/confirm"]


def test_setting_user_quota_immediately_runs_coverage_fill(admin_client, monkeypatch):
    import potato.routes as routes

    class User:
        def __init__(self):
            self.maximum = -1

        def get_annotation_count(self):
            return 1

        def set_max_assignments(self, value):
            self.maximum = value

    target = User()

    class Users:
        def get_user_state(self, username):
            return target

        def get_all_users(self):
            return [target]

        def save_user_state(self, user_state):
            pass

    class Items:
        def fill_assignments_to_coverage(self, users):
            return {
                "new_assignments": 14,
                "total_shortfall": 2,
                "items_below_target": [{"item_id": "x", "missing": 2}],
            }

    monkeypatch.setattr(routes, "get_user_state_manager", lambda: Users())
    monkeypatch.setattr(routes, "get_item_state_manager", lambda: Items())

    response = admin_client.post(
        "/admin/api/user/tester/set_instances",
        headers={"X-API-Key": "audio-import-key"},
        json={"max_instances": 15},
    )

    assert response.status_code == 200
    assert target.maximum == 15
    assert response.get_json()["coverage"]["new_assignments"] == 14
    assert response.get_json()["coverage"]["total_shortfall"] == 2


def test_setting_item_target_updates_running_manager_and_refills(admin_client, monkeypatch):
    import potato.routes as routes

    class Items:
        def __init__(self):
            self.max_annotations_per_item = 1
            self.config = {}

        def fill_assignments_to_coverage(self, users):
            return {"new_assignments": 5, "total_shortfall": 0, "assignments_by_user": {}}

    class Users:
        def get_all_users(self):
            return []

    items = Items()
    monkeypatch.setattr(routes, "get_item_state_manager", lambda: items)
    monkeypatch.setattr(routes, "get_user_state_manager", lambda: Users())
    monkeypatch.setattr(
        routes.admin_dashboard,
        "update_config",
        lambda updates: {"status": "success", "updated_fields": list(updates)},
    )

    response = admin_client.post(
        "/admin/api/config",
        headers={"X-API-Key": "audio-import-key"},
        json={"max_annotations_per_item": 2},
    )

    assert response.status_code == 200
    assert items.max_annotations_per_item == 2
    assert items.config["num_annotators_per_item"] == 2
    assert response.get_json()["coverage"]["new_assignments"] == 5
