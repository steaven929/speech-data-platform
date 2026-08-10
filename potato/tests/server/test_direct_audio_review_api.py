import json
import shutil
from pathlib import Path

import pytest
import requests
import yaml

from tests.helpers.flask_test_setup import FlaskTestServer
from tests.helpers.port_manager import find_free_port


ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "examples" / "audio" / "asr-transcript-correction"


@pytest.fixture(scope="module")
def review_server(tmp_path_factory):
    task = tmp_path_factory.mktemp("direct-audio-review")
    for name in ("config.yaml", "users.jsonl"):
        shutil.copy2(SOURCE / name, task / name)
    config_path = task / "config.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["output_annotation_dir"] = str(task / "annotation_output")
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    shutil.copytree(SOURCE / "data", task / "data")
    shutil.copytree(SOURCE / "media", task / "media")
    (task / "layouts").mkdir()
    server = FlaskTestServer(port=find_free_port(), config_file=str(task / "config.yaml"))
    assert server.start()
    yield server, task
    server.stop()


def login(base_url, username):
    session = requests.Session()
    response = session.post(
        f"{base_url}/auth", data={"email": username, "pass": "123"},
        allow_redirects=False,
    )
    assert response.status_code in (302, 303)
    return session


def seed_annotation(base_url, username="user2", recording_id="20260720151516032"):
    worker = login(base_url, username)
    worker.get(f"{base_url}/annotate")
    payload = {"segments": [{
        "id": "seg-1", "start_time": 1.0, "end_time": 3.0,
        "label": "agent", "text": "修改前", "annotations": {},
    }]}
    response = worker.post(f"{base_url}/updateinstance", json={
        "instance_id": recording_id,
        "annotations": {"transcript_segments:::_data": json.dumps(payload)},
        "span_annotations": [],
    })
    assert response.status_code == 200


def test_admin_claims_edits_completes_and_reopens_original_annotation(review_server):
    server, task = review_server
    seed_annotation(server.base_url)
    admin = login(server.base_url, "admin")

    queue = admin.get(f"{server.base_url}/adjudicate/api/audio-reviews")
    assert queue.status_code == 200
    record = next(item for item in queue.json()["items"] if item["annotator"] == "user2")
    assert record["review_status"] == "pending"

    claim = admin.post(f"{server.base_url}/adjudicate/api/audio-reviews/claim", json={
        "recording_id": record["recording_id"], "annotator": "user2",
    })
    assert claim.status_code == 200
    assert claim.json()["review_status"] == "in_progress"

    edited = {"segments": [{
        "id": "seg-1", "start_time": 0.5, "end_time": 2.75,
        "label": "caller", "text": "管理员修改后", "annotations": {"dialect": True},
    }]}
    update = admin.put(
        f"{server.base_url}/adjudicate/api/audio-reviews/{record['recording_id']}/user2",
        json=edited,
    )
    assert update.status_code == 200, update.text
    assert update.json()["segments"][0]["text"] == "管理员修改后"

    state = json.loads((task / "annotation_output" / "user2" / "user_state.json").read_text())
    assert "管理员修改后" in json.dumps(state, ensure_ascii=False)
    assert len(list((task / "annotation_output" / "admin_review" / "history").glob("*.json"))) == 1

    complete = admin.post(
        f"{server.base_url}/adjudicate/api/audio-reviews/{record['recording_id']}/user2/complete"
    )
    assert complete.status_code == 200
    assert complete.json()["review_status"] == "completed"
    reopen = admin.post(
        f"{server.base_url}/adjudicate/api/audio-reviews/{record['recording_id']}/user2/reopen"
    )
    assert reopen.status_code == 200
    assert reopen.json()["review_status"] == "in_progress"


def test_admin_edits_and_completes_pending_annotation_without_claim(review_server):
    server, _ = review_server
    recording_id = "20260720151906185"
    seed_annotation(server.base_url, "tester_a", recording_id)
    admin = login(server.base_url, "admin")

    edited = {"segments": [{
        "id": "seg-1", "start_time": 0.25, "end_time": 2.5,
        "label": "caller", "text": "待审核直接修改", "annotations": {"dialect": False},
    }]}
    update = admin.put(
        f"{server.base_url}/adjudicate/api/audio-reviews/{recording_id}/tester_a",
        json=edited,
    )
    assert update.status_code == 200, update.text
    assert update.json()["review_status"] == "pending"

    queue = admin.get(f"{server.base_url}/adjudicate/api/audio-reviews").json()["items"]
    saved = next(item for item in queue
                 if item["recording_id"] == recording_id and item["annotator"] == "tester_a")
    assert saved["segments"][0]["text"] == "待审核直接修改"
    complete = admin.post(
        f"{server.base_url}/adjudicate/api/audio-reviews/{recording_id}/tester_a/complete"
    )
    assert complete.status_code == 200
    assert complete.json()["review_status"] == "completed"
    assert complete.json()["reviewed_by"] == "admin"
    assert complete.json()["assigned_to"] is None


def test_annotator_cannot_access_direct_review_api(review_server):
    server, _ = review_server
    worker = login(server.base_url, "tester_a")
    assert worker.get(f"{server.base_url}/adjudicate/api/audio-reviews").status_code == 403


def test_asr_adjudication_page_has_direct_edit_controls(review_server):
    server, _ = review_server
    admin = login(server.base_url, "admin")
    response = admin.get(f"{server.base_url}/adjudicate")
    assert response.status_code == 200
    for text in ("分配给自己", "保存修改", "设为最终结果", "重新编辑"):
        assert text in response.text
    assert "direct-audio-review.js" in response.text
