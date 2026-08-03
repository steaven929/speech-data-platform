import shutil
import sqlite3
from pathlib import Path

import pytest
import requests

from tests.helpers.flask_test_setup import FlaskTestServer
from tests.helpers.port_manager import find_free_port


ROOT = Path(__file__).parents[2]
SOURCE_TASK = ROOT / "examples" / "audio" / "asr-transcript-correction"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    task_dir = tmp_path_factory.mktemp("asr-admin-workflow")
    for name in ("config.yaml", "users.jsonl"):
        shutil.copy2(SOURCE_TASK / name, task_dir / name)
    shutil.copytree(SOURCE_TASK / "data", task_dir / "data")
    shutil.copytree(SOURCE_TASK / "media", task_dir / "media")
    (task_dir / "layouts").mkdir()

    instance = FlaskTestServer(
        port=find_free_port(),
        config_file=str(task_dir / "config.yaml"),
    )
    assert instance.start()
    yield instance
    instance.stop()


def login(base_url, username, password="123"):
    session = requests.Session()
    response = session.post(
        f"{base_url}/auth",
        data={"email": username, "pass": password},
        allow_redirects=False,
    )
    assert response.status_code in (302, 303)
    return session


def test_all_preconfigured_accounts_can_log_in(server):
    for username in ("admin", "user2", "tester_a", "tester_b"):
        session = login(server.base_url, username)
        assert session.get(f"{server.base_url}/annotate").status_code == 200


def test_unknown_account_cannot_log_in(server):
    response = requests.post(
        f"{server.base_url}/auth",
        data={"email": "unknown", "pass": "123"},
        allow_redirects=False,
    )
    assert response.status_code == 200
    assert "用户名或密码错误" in response.text


def test_annotator_cannot_open_admin(server):
    session = login(server.base_url, "user2")
    response = session.get(f"{server.base_url}/admin")
    assert response.status_code == 200
    assert "admin-login" in response.text or "管理密钥" in response.text


def test_admin_can_open_admin_and_set_annotator_quota(server):
    worker = login(server.base_url, "tester_a")
    worker.get(f"{server.base_url}/annotate")

    admin = login(server.base_url, "admin")
    dashboard = admin.get(f"{server.base_url}/admin")
    assert dashboard.status_code == 200
    assert "admin-login" not in dashboard.text

    response = admin.post(
        f"{server.base_url}/admin/api/user/tester_a/set_instances",
        json={"max_instances": 2},
    )
    assert response.status_code == 200
    assert response.json()["max_instances"] == 2


def test_admin_page_contains_annotation_data_controls(server):
    admin = login(server.base_url, "admin")
    response = admin.get(f"{server.base_url}/admin")
    assert response.status_code == 200
    for text in (
        "标注数据",
        "按标注员筛选",
        "录音编号",
        "片段文本",
        "导出 JSON",
        "导出 SQLite",
    ):
        assert text in response.text


def test_admin_and_review_pages_do_not_ship_known_english_ui_labels(server):
    admin = login(server.base_url, "admin")
    dashboard = admin.get(f"{server.base_url}/admin")
    review = admin.get(f"{server.base_url}/adjudicate")

    for text in (
        "Total Annotations",
        "Items with Annotations",
        "Unsupported annotation type",
        "Users with Data",
        "Total Interactions",
        "Total Workers",
        "No crowdsourcing workers detected",
        "System Configuration",
        "Configuration updated successfully",
    ):
        assert text not in dashboard.text

    for text in ("审核队列", "待审核", "保存修改", "审核通过"):
        assert text in review.text


def test_annotator_cannot_set_quota(server):
    worker = login(server.base_url, "user2")
    assert (
        worker.get(f"{server.base_url}/admin/api/annotators").status_code == 403
    )
    response = worker.post(
        f"{server.base_url}/admin/api/user/tester_a/set_instances",
        json={"max_instances": 5},
    )
    assert response.status_code == 403


def test_admin_has_zero_annotation_quota(server):
    admin = login(server.base_url, "admin")
    overview = admin.get(f"{server.base_url}/admin/api/annotators")
    assert overview.status_code == 200
    admin_row = next(
        annotator
        for annotator in overview.json()["annotators"]
        if annotator["user_id"] == "admin"
    )
    assert admin_row["max_assignments"] == 0


def test_admin_can_view_and_download_saved_audio_annotations(server, tmp_path):
    worker = login(server.base_url, "user2")
    worker.get(f"{server.base_url}/annotate")
    saved_data = (
        '{"segments":[{"id":"seg-1","start_time":1.5,"end_time":3.25,'
        '"label":"agent","text":"管理员可见文本","annotations":{"dialect":true}}]}'
    )
    save_response = worker.post(
        f"{server.base_url}/updateinstance",
        json={
            "instance_id": "20260720151516032",
            "annotations": {
                "transcript_segments:::_data": saved_data,
            },
            "span_annotations": {},
        },
    )
    assert save_response.status_code == 200

    admin = login(server.base_url, "admin")
    list_response = admin.get(
        f"{server.base_url}/admin/api/annotation-data",
        params={"annotator": "user2", "recording_id": "20260720151516032"},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["summary"] == {
        "recording_count": 1,
        "annotation_count": 1,
        "segment_count": 1,
    }
    assert payload["annotations"][0]["segments"][0]["text"] == "管理员可见文本"

    json_response = admin.get(
        f"{server.base_url}/admin/api/annotation-data/export/json"
    )
    assert json_response.status_code == 200
    assert "attachment" in json_response.headers["Content-Disposition"]
    assert json_response.json()["annotations"][0]["annotator"] == "user2"

    sqlite_response = admin.get(
        f"{server.base_url}/admin/api/annotation-data/export/sqlite"
    )
    assert sqlite_response.status_code == 200
    database_path = tmp_path / "download.sqlite"
    database_path.write_bytes(sqlite_response.content)
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT a.recording_id, a.annotator, s.text
            FROM annotations a
            JOIN segments s ON s.annotation_id = a.id
            """
        ).fetchone()
    assert row == ("20260720151516032", "user2", "管理员可见文本")


def test_annotator_cannot_view_or_export_annotation_data(server):
    worker = login(server.base_url, "tester_a")
    assert (
        worker.get(f"{server.base_url}/admin/api/annotation-data").status_code
        == 403
    )
    assert (
        worker.get(
            f"{server.base_url}/admin/api/annotation-data/export/json"
        ).status_code
        == 403
    )
