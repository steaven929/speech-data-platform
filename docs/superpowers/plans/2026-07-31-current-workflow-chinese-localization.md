# Current Workflow Chinese Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fully localize the ASR project's login, annotation, admin, and adjudication interfaces into Chinese without changing behavior or data contracts.

**Architecture:** Extend the ASR project's existing `ui_language` configuration for shared text, then localize only the core templates and JavaScript used by the four active pages. Add page-level characterization tests so English regressions are detected without changing API fields, URLs, account names, or exported JSON keys.

**Tech Stack:** Flask, Jinja2, JavaScript, YAML, pytest, requests.

## Global Constraints

- Do not change layouts, permissions, task assignment, annotation data, or export schemas.
- Keep account names, recording IDs, URLs, source identifiers, and JSON keys unchanged.
- Use consistent Chinese terms: 管理员、标注员、审核、待审核、审核中、已完成、跳过、置信度.
- Do not localize unused Potato modules.

---

### Task 1: Characterize the four active pages

**Files:**
- Create: `potato/tests/server/test_asr_chinese_ui.py`
- Read: `potato/examples/audio/asr-transcript-correction/config.yaml`

**Interfaces:**
- Consumes: the real ASR config and authenticated Flask sessions.
- Produces: assertions for required Chinese text and forbidden primary English controls.

- [ ] Write a server fixture using the real ASR config copied into a temporary task directory.
- [ ] Log in as `admin` and `user2`, then request `/`, `/annotate`, `/admin`, and `/adjudicate`.
- [ ] Assert each page contains its required Chinese headings and controls.
- [ ] Assert primary English labels such as `Queue`, `Pending`, `Done`, `Logout`, `Confidence`, `Skip`, `Submit and continue`, and `Assignments` are absent.
- [ ] Run `pytest tests/server/test_asr_chinese_ui.py -v` and confirm the current English pages fail.

### Task 2: Localize shared login and annotation text

**Files:**
- Modify: `potato/examples/audio/asr-transcript-correction/config.yaml`
- Modify only when configuration cannot cover a visible string: `potato/potato/templates/id_login_home.html`
- Modify only when configuration cannot cover a visible string: `potato/potato/static/annotation.js`

**Interfaces:**
- Consumes: `ui_language` keys exposed by the generated annotation template.
- Produces: Chinese login, navigation, annotation status, waveform, segment, help, validation, and browser feedback.

- [ ] Add all supported login and annotation language keys to `ui_language`.
- [ ] Replace remaining hard-coded visible English text only in the active login and annotation paths.
- [ ] Preserve JavaScript variable names, request fields, and API routes.
- [ ] Run the login and annotation cases in `test_asr_chinese_ui.py`.
- [ ] Commit the localized login and annotation interface.

### Task 3: Localize the admin interface

**Files:**
- Modify: `potato/potato/templates/admin.html`
- Modify: `potato/potato/templates/admin_login.html`
- Modify only if it contains active admin labels: `potato/potato/static/admin.js`
- Test: `potato/tests/server/test_asr_chinese_ui.py`

**Interfaces:**
- Consumes: the existing admin dashboard APIs and session/RBAC state.
- Produces: Chinese dashboard navigation, headings, quota controls, progress states, dialogs, and errors.

- [ ] Translate the admin login screen and the dashboard sections reachable in the ASR workflow.
- [ ] Translate quota, assignment, annotator, progress, action, loading, success, and failure text.
- [ ] Leave API payload keys and status values unchanged; map them only at render time.
- [ ] Run admin UI and existing admin/RBAC workflow tests.
- [ ] Commit the localized admin interface.

### Task 4: Localize the adjudication interface

**Files:**
- Modify: `potato/potato/templates/adjudication.html`
- Modify: `potato/potato/static/adjudication.js`
- Modify: `potato/potato/static/adjudication-forms.js`
- Test: `potato/tests/server/test_asr_chinese_ui.py`

**Interfaces:**
- Consumes: `/adjudicate/api/*` responses without changing their schema.
- Produces: Chinese queue filters, item details, annotator responses, review controls, confidence, notes, skip/submit feedback, and empty/completed states.

- [ ] Translate all static template text on `/adjudicate`.
- [ ] Translate dynamically generated JavaScript text, alerts, empty states, and status labels.
- [ ] Keep schema names, annotator names, IDs, and source values unchanged.
- [ ] Run Chinese UI, audio adjudication, and export tests.
- [ ] Commit the localized adjudication interface.

### Task 5: Browser verification and restart

**Files:**
- No source files unless verification exposes a missed visible string.

**Interfaces:**
- Consumes: the running ASR service at port 8012.
- Produces: verified Chinese login, annotation, admin, and adjudication pages.

- [ ] Run the focused localization and workflow suites.
- [ ] Run `git diff --check` and verify runtime files are not staged.
- [ ] Restart the service on port 8012.
- [ ] Log in as `admin` and `user2`; inspect all four active pages.
- [ ] Verify the existing test recording remains visible in the audit queue.
- [ ] Commit any final text-only corrections.
