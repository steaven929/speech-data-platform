"""Characterize the Chinese UI contract for the active ASR workflow."""

import shutil
from pathlib import Path

import pytest
import requests

from tests.helpers.flask_test_setup import FlaskTestServer
from tests.helpers.port_manager import find_free_port


ROOT = Path(__file__).parents[2]
SOURCE_TASK = ROOT / "examples" / "audio" / "asr-transcript-correction"


@pytest.fixture(scope="module")
def asr_server(tmp_path_factory):
    """Run the real ASR task from an isolated copy of its configuration."""
    task_dir = tmp_path_factory.mktemp("asr-chinese-ui")
    for name in ("config.yaml", "users.jsonl"):
        shutil.copy2(SOURCE_TASK / name, task_dir / name)
    for name in ("data", "media"):
        shutil.copytree(SOURCE_TASK / name, task_dir / name)
    (task_dir / "layouts").mkdir()

    server = FlaskTestServer(
        port=find_free_port(),
        config_file=str(task_dir / "config.yaml"),
    )
    assert server.start()
    yield server
    server.stop()


def login(base_url, username, password="123"):
    session = requests.Session()
    response = session.post(
        f"{base_url}/auth",
        data={"email": username, "pass": password},
        allow_redirects=False,
    )
    assert response.status_code in (302, 303)
    return session


def assert_contains_all(page, expected_text):
    for text in expected_text:
        assert text in page


def assert_contains_none(page, forbidden_text):
    for text in forbidden_text:
        assert text not in page


def test_login_page_uses_chinese_labels(asr_server):
    """The entry page must present the ASR login journey in Chinese."""
    response = requests.get(f"{asr_server.base_url}/")

    assert response.status_code == 200
    assert_contains_all(response.text, ("语音标注平台", "用户名", "密码", "登录"))
    assert_contains_none(response.text, ("Login", "Password", "Username"))


def test_annotation_page_uses_chinese_navigation(asr_server):
    """Annotators must see Chinese navigation and task guidance."""
    response = login(asr_server.base_url, "user2").get(
        f"{asr_server.base_url}/annotate"
    )

    assert response.status_code == 200
    assert_contains_all(response.text, ("下一条", "上一条", "退出", "标注说明"))
    assert_contains_none(response.text, ("Logout", "Next", "Previous", "Instructions"))


def test_admin_page_uses_chinese_dashboard_labels(asr_server):
    """Administrators must see Chinese dashboard and quota controls."""
    response = login(asr_server.base_url, "admin").get(
        f"{asr_server.base_url}/admin"
    )

    assert response.status_code == 200
    assert_contains_all(response.text, ("管理后台", "标注员", "任务配额", "退出"))
    assert_contains_none(response.text, ("Logout", "Annotators", "Assignments"))


def test_adjudication_page_uses_chinese_review_controls(asr_server):
    """Administrators must see Chinese review queue and decision controls."""
    response = login(asr_server.base_url, "admin").get(
        f"{asr_server.base_url}/adjudicate"
    )

    assert response.status_code == 200
    assert_contains_all(response.text, ("审核", "待审核", "已完成", "置信度", "跳过", "提交并继续"))
    assert_contains_none(
        response.text,
        ("Queue", "Pending", "Done", "Logout", "Confidence", "Skip", "Submit and continue"),
    )
