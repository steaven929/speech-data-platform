"""Characterize the Chinese UI contract for the active ASR workflow."""

import shutil
from pathlib import Path

import pytest
import requests
from bs4 import BeautifulSoup

from tests.helpers.flask_test_setup import FlaskTestServer
from tests.helpers.port_manager import find_free_port


ROOT = Path(__file__).parents[2]
SOURCE_TASK = ROOT / "examples" / "audio" / "asr-transcript-correction"


@pytest.fixture(scope="module")
def asr_server(tmp_path_factory):
    """Run the real ASR task from an isolated copy of its configuration."""
    task_dir = tmp_path_factory.mktemp("asr-chinese-ui")
    for name in ("config.yaml", "users.jsonl", "admin_api_key.txt"):
        shutil.copy2(SOURCE_TASK / name, task_dir / name)
    for name in ("data", "media"):
        shutil.copytree(SOURCE_TASK / name, task_dir / name)
    (task_dir / "layouts").mkdir()

    server = FlaskTestServer(
        port=find_free_port(),
        config_file=str(task_dir / "config.yaml"),
    )
    assert server.start()
    server.asr_admin_api_key = (task_dir / "admin_api_key.txt").read_text().strip()
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


def page_soup(page):
    return BeautifulSoup(page, "html.parser")


def element_text(page, selector):
    element = page_soup(page).select_one(selector)
    assert element is not None, f"Expected visible UI element {selector!r}"
    return " ".join(element.stripped_strings)


def assert_element_text(page, selector, expected):
    assert element_text(page, selector) == expected


def assert_element_text_is_not(page, selector, forbidden):
    assert element_text(page, selector) != forbidden


def assert_element_attribute(page, selector, attribute, expected):
    element = page_soup(page).select_one(selector)
    assert element is not None, f"Expected visible UI element {selector!r}"
    assert element.get(attribute) == expected


def test_login_page_uses_chinese_labels(asr_server):
    """The entry page must present the ASR login journey in Chinese."""
    response = requests.get(f"{asr_server.base_url}/")

    assert response.status_code == 200
    assert_element_text(response.text, ".potato-page-title", "语音标注平台")
    assert_element_text(response.text, "label[for='login-email']", "用户名")
    assert_element_text(response.text, "label[for='login-pass']", "密码")
    assert_element_text(response.text, "#login-content button[type='submit']", "登录")
    assert_element_text_is_not(response.text, "#login-content button[type='submit']", "Login")


def test_annotation_page_uses_chinese_navigation(asr_server):
    """Annotators must see Chinese navigation and task guidance."""
    response = login(asr_server.base_url, "user2").get(
        f"{asr_server.base_url}/annotate"
    )

    assert response.status_code == 200
    assert_element_text(response.text, "#next-btn", "下一条")
    assert_element_text(response.text, ".logout-btn", "退出")
    assert_element_attribute(
        response.text, ".playback-rate-select", "title", "调整播放速度"
    )
    assert_element_text_is_not(response.text, ".logout-btn", "Logout")


def test_admin_page_uses_chinese_dashboard_labels(asr_server):
    """Administrators must see Chinese dashboard and quota controls."""
    admin_session = login(asr_server.base_url, "admin")
    response = admin_session.get(
        f"{asr_server.base_url}/admin",
        headers={"X-API-Key": asr_server.asr_admin_api_key},
    )

    assert response.status_code == 200
    assert page_soup(response.text).select_one(".admin-container") is not None
    assert_element_text(response.text, ".admin-header h1", "📊 靖江热线 ASR 转写校对 - 管理后台")
    assert_element_text(response.text, ".admin-tab[data-tab='annotators']", "标注员")
    assert_element_text(response.text, "label[for='assignmentStrategy']", "任务配额")
    assert_element_text(response.text, ".header-actions button", "退出")
    assert_element_text_is_not(response.text, ".admin-tab[data-tab='annotators']", "Annotators")
    assert_element_text_is_not(response.text, "label[for='assignmentStrategy']", "Assignments")


def test_adjudication_page_uses_chinese_review_controls(asr_server):
    """Administrators must see Chinese review queue and decision controls."""
    response = login(asr_server.base_url, "admin").get(
        f"{asr_server.base_url}/adjudicate"
    )

    assert response.status_code == 200
    assert "审核" in element_text(response.text, ".task-name")
    assert_element_text(response.text, "button[data-filter='pending']", "待审核")
    assert_element_text(response.text, "button[data-filter='all']", "审核中")
    assert_element_text(response.text, "button[data-filter='completed']", "已完成")
    assert_element_text(response.text, "label[for='adj-confidence']", "置信度")
    assert_element_text(response.text, "#adj-btn-skip", "跳过")
    assert_element_text(response.text, "#adj-btn-submit", "提交并继续")
    assert_element_text(response.text, ".logout-btn", "退出")
    assert_element_text_is_not(response.text, "button[data-filter='pending']", "Pending")
    assert_element_text_is_not(response.text, "#adj-btn-skip", "Skip")
    assert_element_text_is_not(response.text, "#adj-btn-submit", "Submit and continue")
