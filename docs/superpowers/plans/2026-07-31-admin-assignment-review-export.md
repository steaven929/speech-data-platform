# Admin Assignment, Review, and Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure the ASR project so authenticated annotators receive automatically balanced work while an authenticated administrator controls quotas, reviews every doubly annotated recording, and exports final JSON.

**Architecture:** Reuse Potato's built-in in-memory password authentication, RBAC, admin dashboard, `least_annotated` item manager, adjudication queue, and export layer. Keep all project-specific behavior in the ASR example configuration and its hashed JSONL user file; change core code only if a characterization test proves that audio segment annotations cannot round-trip through adjudication or final export.

**Tech Stack:** Python 3.9, Flask, PyYAML, pytest, Potato RBAC, ItemStateManager, adjudication manager, JSON export.

## Global Constraints

- Accounts are `admin`, `user2`, `tester_a`, and `tester_b`.
- The initial password for all four accounts is `123`; it is only for local testing.
- User credentials must store salted password hashes, never plaintext passwords.
- `admin` has the built-in `admin` RBAC role; all other accounts have the built-in `annotator` role.
- Assignment uses `least_annotated`; every item targets exactly two annotators.
- The administrator sets each annotator's maximum assignment count in `/admin`.
- All items with two completed annotations enter `/adjudicate`, including unanimous items.
- The final JSON contains recording ID, segment start/end, speaker, and transcript text.
- Existing ASR left/right annotation layout and interaction must not regress.

---

### Task 1: Secure accounts, roles, and project configuration

**Files:**
- Modify: `potato/examples/audio/asr-transcript-correction/config.yaml`
- Create: `potato/examples/audio/asr-transcript-correction/users.jsonl`
- Modify: `potato/examples/audio/asr-transcript-correction/.gitignore`
- Create: `potato/tests/unit/test_asr_admin_workflow_config.py`

**Interfaces:**
- Consumes: `UserAuthenticator`, `RBACManager`, and `validate_config`.
- Produces: a valid ASR configuration with closed password authentication, named RBAC roles, two-person coverage, full adjudication, and JSON export.

- [ ] **Step 1: Write the failing configuration test**

```python
from pathlib import Path
import json
import yaml

from potato.authentication import UserAuthenticator
from potato.server_utils.config_module import load_and_validate_config
from potato.server_utils.rbac import RBACManager, Permission

ROOT = Path(__file__).parents[2]
TASK = ROOT / "examples/audio/asr-transcript-correction"


def load_config():
    with (TASK / "config.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_asr_admin_workflow_config_is_closed_and_reviewable():
    cfg = load_and_validate_config(str(TASK / "config.yaml"), str(TASK))
    assert cfg["require_password"] is True
    assert cfg["user_config"]["allow_all_users"] is False
    assert cfg["authentication"]["user_config_path"].endswith("users.jsonl")
    assert cfg["assignment_strategy"] == "least_annotated"
    assert cfg["num_annotators_per_item"] == 2
    assert cfg["adjudication"]["enabled"] is True
    assert cfg["adjudication"]["show_all_items"] is True
    assert cfg["adjudication"]["min_annotations"] == 2
    assert cfg["export_annotation_format"] == "json"


def test_asr_roles_separate_admin_and_annotators():
    cfg = load_config()
    rbac = RBACManager(cfg)
    assert rbac.get_roles_for_user("admin") == {"admin"}
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
    assert {r["username"] for r in records} == {
        "admin", "user2", "tester_a", "tester_b"
    }
    assert all(r["password"] != "123" and "$" in r["password"] for r in records)
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd potato
.venv/bin/python -m pytest tests/unit/test_asr_admin_workflow_config.py -v
```

Expected: failures because password auth, RBAC, coverage, adjudication, modern export, and `users.jsonl` are not configured.

- [ ] **Step 3: Generate the four salted password hashes**

Run from the repository's `potato/` directory:

```bash
PYTHONPATH=. .venv/bin/python -c '
import json
from potato.authentication import _hash_password_with_salt
for username in ("admin", "user2", "tester_a", "tester_b"):
    print(json.dumps({"username": username, "password": _hash_password_with_salt("123")}))
'
```

Copy the four generated JSON objects verbatim into `examples/audio/asr-transcript-correction/users.jsonl`, one object per line.

- [ ] **Step 4: Add the minimal project configuration**

Add or replace these settings in `config.yaml`:

```yaml
require_password: true

authentication:
  method: in_memory
  user_config_path: users.jsonl

user_config:
  allow_all_users: false
  users: [admin, user2, tester_a, tester_b]

assignment_strategy: least_annotated
num_annotators_per_item: 2

rbac:
  enabled: true
  user_role_assignments:
    admin: admin
    user2: annotator
    tester_a: annotator
    tester_b: annotator

adjudication:
  enabled: true
  adjudicator_users: [admin]
  min_annotations: 2
  agreement_threshold: 1.0
  show_all_items: true
  show_annotator_names: true
  show_timing_data: true
  show_agreement_scores: true
  require_confidence: true
  output_subdir: adjudication

export_annotation_format: json
```

Remove the legacy `output_annotation_format` key. Ensure `.gitignore` ignores runtime-only `annotation_output/`, `waveform_cache/`, `project.sqlite`, and `admin_api_key.txt`, but does not ignore `users.jsonl`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_asr_admin_workflow_config.py \
  tests/unit/test_rbac_manager.py \
  tests/server/test_rbac_routes.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add \
  examples/audio/asr-transcript-correction/config.yaml \
  examples/audio/asr-transcript-correction/users.jsonl \
  examples/audio/asr-transcript-correction/.gitignore \
  tests/unit/test_asr_admin_workflow_config.py
git commit -m "feat: configure secure ASR admin workflow"
```

---

### Task 2: Verify quota assignment and route permissions

**Files:**
- Create: `potato/tests/server/test_asr_admin_workflow.py`
- Modify only if tests expose a defect: `potato/potato/routes.py`
- Modify only if tests expose a defect: `potato/potato/item_state_management.py`

**Interfaces:**
- Consumes: authenticated Flask sessions, `/admin/api/user/<username>/set_instances`, ItemStateManager, RBAC.
- Produces: verified admin-only quota management and two-person `least_annotated` assignment.

- [ ] **Step 1: Add an integration fixture using the real ASR config**

```python
from pathlib import Path
import pytest
import requests

from tests.helpers.flask_test_setup import FlaskTestServer
from tests.helpers.port_manager import find_free_port

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "examples/audio/asr-transcript-correction/config.yaml"


@pytest.fixture(scope="module")
def server():
    instance = FlaskTestServer(
        port=find_free_port(),
        config_file=str(CONFIG),
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
```

- [ ] **Step 2: Add permission and quota tests**

```python
def test_annotator_cannot_open_admin(server):
    session = login(server.base_url, "user2")
    assert session.get(f"{server.base_url}/admin").status_code in (302, 403)


def test_admin_can_set_annotator_quota(server):
    worker = login(server.base_url, "tester_a")
    worker.get(f"{server.base_url}/annotate")
    admin = login(server.base_url, "admin")
    response = admin.post(
        f"{server.base_url}/admin/api/user/tester_a/set_instances",
        json={"max_instances": 2},
    )
    assert response.status_code == 200
    assert response.json()["max_instances"] == 2


def test_annotator_cannot_set_quota(server):
    worker = login(server.base_url, "user2")
    response = worker.post(
        f"{server.base_url}/admin/api/user/tester_a/set_instances",
        json={"max_instances": 5},
    )
    assert response.status_code in (302, 403)
```

- [ ] **Step 3: Run tests and characterize failures**

Run:

```bash
.venv/bin/python -m pytest tests/server/test_asr_admin_workflow.py -v
```

Expected: RBAC blocks annotators, admin changes quotas, and assignment remains capped at two users per item.

- [ ] **Step 4: If a test fails, implement only the missing guard or assignment behavior**

Use the existing RBAC decorator:

```python
@require_permission(Permission.MANAGE_ASSIGNMENT)
def admin_api_set_user_instances(username):
    ...
```

Do not add a new admin page or a second assignment system.

- [ ] **Step 5: Re-run tests and commit**

```bash
.venv/bin/python -m pytest \
  tests/server/test_asr_admin_workflow.py \
  tests/server/test_rbac_routes.py \
  tests/unit/test_item_state_manager.py -v
git add tests/server/test_asr_admin_workflow.py potato/routes.py potato/item_state_management.py
git commit -m "test: verify ASR admin quota assignment"
```

Stage implementation files only when they actually changed.

---

### Task 3: Prove audio annotations round-trip through full review

**Files:**
- Create: `potato/tests/server/test_asr_audio_adjudication.py`
- Modify only if needed: `potato/potato/adjudication.py`
- Modify only if needed: `potato/potato/templates/adjudication.html`
- Modify only if needed: `potato/potato/static/adjudication.js`

**Interfaces:**
- Consumes: two persisted audio segment annotations and the existing adjudication API.
- Produces: an administrator decision containing the complete audio segment list.

- [ ] **Step 1: Add a focused audio adjudication round-trip test**

Create two user results for the same recording with this shape:

```python
segments_a = [
    {"start": 0.0, "end": 1.2, "label": "caller", "text": "你好"},
    {"start": 1.3, "end": 2.5, "label": "agent", "text": "您好"},
]
segments_b = [
    {"start": 0.0, "end": 1.1, "label": "caller", "text": "你好"},
    {"start": 1.2, "end": 2.5, "label": "agent", "text": "您好"},
]
```

The test must assert:

```python
assert queue_item["num_annotators"] == 2
assert detail["annotations"]["user2"]["transcript_segments"] == segments_a
assert detail["annotations"]["tester_a"]["transcript_segments"] == segments_b

decision = {
    "instance_id": recording_id,
    "final_annotation": {"transcript_segments": segments_a},
    "confidence": "high",
    "notes": "full review",
}
response = admin.post(f"{base_url}/adjudicate/api/decision", json=decision)
assert response.status_code == 200
assert saved["final_annotation"]["transcript_segments"] == segments_a
```

- [ ] **Step 2: Run the test and verify current behavior**

Run:

```bash
.venv/bin/python -m pytest tests/server/test_asr_audio_adjudication.py -v
```

Expected: pass if the generic adjudication data model preserves nested audio segments; otherwise fail at the first lossy boundary.

- [ ] **Step 3: Implement the smallest compatibility fix if required**

Preserve annotation values as JSON-compatible nested objects:

```python
def _copy_annotation_value(value):
    return json.loads(json.dumps(value, ensure_ascii=False))
```

Use the helper only at the proven lossy boundary. The adjudication UI must render each candidate segment's start, end, label, and text without flattening or stringifying the value.

- [ ] **Step 4: Run adjudication regression tests**

```bash
.venv/bin/python -m pytest \
  tests/server/test_asr_audio_adjudication.py \
  tests/server/test_adjudication_api.py \
  tests/server/test_adjudication_phase3_api.py \
  tests/unit/test_adjudication.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add \
  tests/server/test_asr_audio_adjudication.py \
  potato/adjudication.py \
  potato/templates/adjudication.html \
  potato/static/adjudication.js
git commit -m "feat: support full audio annotation review"
```

Stage only files that changed.

---

### Task 4: Validate final JSON export and browser workflow

**Files:**
- Create: `potato/tests/server/test_asr_adjudicated_export.py`
- Modify only if needed: `potato/potato/adjudication_export.py`
- Modify only if needed: `potato/potato/export/`
- Create: `potato/examples/audio/asr-transcript-correction/README.md`

**Interfaces:**
- Consumes: unanimous and administrator-reviewed adjudication decisions.
- Produces: final JSON with complete audio segment data and explicit handling of incomplete items.

- [ ] **Step 1: Add export assertions**

```python
def test_final_export_preserves_reviewed_audio_segments(exported_rows):
    row = exported_rows[0]
    assert row["id"]
    segments = row["transcript_segments"]
    assert segments
    assert set(segments[0]) >= {"start", "end", "label", "text"}
    assert row["source"] in {"unanimous", "adjudicated"}


def test_unreviewed_items_are_not_silently_final(exported_rows):
    assert all(row["source"] != "unresolved" for row in exported_rows)
```

- [ ] **Step 2: Run the test and implement only a proven export gap**

```bash
.venv/bin/python -m pytest tests/server/test_asr_adjudicated_export.py -v
```

If nested segments are lost, update the adjudicated export adapter to copy `transcript_segments` unchanged. If unresolved items are included by default, change the ASR export invocation to exclude them and report their count.

- [ ] **Step 3: Document the operator workflow**

Add these exact steps to the example README:

```text
1. Start the ASR project.
2. Log in as admin and open /admin.
3. Set each annotator's maximum assignments.
4. Annotators complete work at /annotate.
5. Log in as admin and open /adjudicate.
6. Review every item after it has two annotations.
7. Export the adjudicated JSON and confirm there are no unresolved items.
8. Replace the test password before shared use.
```

- [ ] **Step 4: Run the focused automated suite**

```bash
.venv/bin/python -m pytest \
  tests/unit/test_asr_admin_workflow_config.py \
  tests/server/test_asr_admin_workflow.py \
  tests/server/test_asr_audio_adjudication.py \
  tests/server/test_asr_adjudicated_export.py -v
```

Expected: all pass.

- [ ] **Step 5: Run browser smoke tests**

Start the service on a free port and verify:

```text
admin / 123      → /admin returns 200
user2 / 123      → /annotate returns 200
user2            → /admin is denied
admin            → /adjudicate returns 200
two annotations  → item appears in full-review queue
admin decision   → final JSON export contains all audio segments
```

- [ ] **Step 6: Run regression tests**

```bash
.venv/bin/python -m pytest \
  tests/unit/test_audio_annotation_schema.py \
  tests/unit/test_schema_registry_integration.py \
  tests/server/test_rbac_routes.py \
  tests/server/test_adjudication_api.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add \
  tests/server/test_asr_adjudicated_export.py \
  potato/adjudication_export.py \
  potato/export \
  examples/audio/asr-transcript-correction/README.md
git commit -m "docs: complete ASR admin review workflow"
```

Stage only files that changed.

---

## Final verification

- [ ] Run `git diff --check`.
- [ ] Run `git status --short` and confirm runtime artifacts are not staged.
- [ ] Confirm no plaintext password `123` exists in `users.jsonl`.
- [ ] Confirm the four focused workflow tests pass.
- [ ] Confirm the audio schema and adjudication regression suites pass.
- [ ] Restart the service from the feature branch and complete one browser smoke cycle.
