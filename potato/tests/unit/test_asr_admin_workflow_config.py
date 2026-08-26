import json
from pathlib import Path

import yaml

from potato.server_utils.config_module import load_and_validate_config
from potato.server_utils.rbac import Permission, RBACManager


ROOT = Path(__file__).parents[2]
TASK = ROOT / "examples" / "audio" / "asr-transcript-correction"


def load_config():
    with (TASK / "config.yaml").open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def test_asr_admin_workflow_config_is_closed_and_reviewable():
    config = load_and_validate_config(str(TASK / "config.yaml"), str(TASK))

    assert config["require_password"] is True
    assert config["user_config"]["allow_all_users"] is False
    assert config["authentication"]["user_config_path"].endswith("users.jsonl")
    assert config["assignment_strategy"] == "least_annotated"
    assert config["num_annotators_per_item"] == 2
    assert config["per_annotator_quota"]["by_user"]["admin"] == 0
    assert config["adjudication"]["enabled"] is True
    assert config["adjudication"]["show_all_items"] is True
    assert config["adjudication"]["min_annotations"] == 2
    assert config["export_annotation_format"] == "json"


def test_asr_roles_separate_admin_and_annotators():
    rbac = RBACManager(load_config())

    assert rbac.get_roles_for_user("admin") == {"admin", "adjudicator"}
    assert rbac.get_roles_for_user("user2") == {"annotator"}
    assert rbac.has_permission("admin", Permission.MANAGE_ASSIGNMENT)
    assert rbac.has_permission("admin", Permission.ADJUDICATE)
    assert not rbac.has_permission("user2", Permission.VIEW_ADMIN_DASHBOARD)


def test_preconfigured_users_use_salted_hashes():
    records = [
        json.loads(line)
        for line in (TASK / "users.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert {record["username"] for record in records} == {
        "admin",
        "user2",
        "annotator_a",
        "annotator_b",
    }
    assert all(
        record["password"] != "123" and "$" in record["password"]
        for record in records
    )
