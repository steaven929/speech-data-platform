import shutil
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
