# 管理员直接修改标注结果 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让管理员领取每个“录音 + 标注员”审核任务，直接修改原音频片段标注，并持久化审核状态与修改前快照。

**Architecture:** 新建独立 `DirectAudioReviewStore` 管理领取、状态和历史，不把审核状态混入通用 adjudication 决策模型。Flask 路由把管理员操作映射到该服务；ASR 配置开启后，`/adjudicate` 使用专用音频审核界面和 API，其他项目继续使用原通用审核逻辑。

**Tech Stack:** Python 3、Flask、JSON 原子存储、原生 JavaScript、pytest/requests

## Global Constraints

- 管理员编辑直接覆盖标注员原始 `transcript_segments:_data`。
- 每次覆盖前必须保存完整旧值及管理员、时间、录音编号、标注员。
- 保存修改和审核通过是两个独立动作。
- 一份已保存标注即可形成一条审核任务；无标注录音不入队。
- 普通标注员不能读取或修改审核数据。
- 不影响非音频项目现有 adjudication 行为。
- 不覆盖当前 `flask_server.py` 的用户未提交改动。

---

### Task 1: 审核状态与历史存储

**Files:**
- Create: `potato/potato/direct_audio_review.py`
- Create: `potato/tests/unit/test_direct_audio_review.py`

**Interfaces:**
- Produces: `DirectAudioReviewStore(output_dir)`
- Produces: `list_reviews(records) -> list[dict]`
- Produces: `claim(recording_id, annotator, admin) -> dict`
- Produces: `complete(recording_id, annotator, admin) -> dict`
- Produces: `reopen(recording_id, annotator, admin) -> dict`
- Produces: `record_snapshot(recording_id, annotator, admin, old_value) -> dict`

- [ ] Write tests proving one record per recording/annotator, exclusive claim, persistent status after reload, completion/reopen, and immutable snapshots.
- [ ] Run `python -m pytest tests/unit/test_direct_audio_review.py -q`; expect import failure.
- [ ] Implement atomic JSON persistence at `annotation_output/admin_review/review_state.json` and append-only snapshot files under `history/`.
- [ ] Re-run the unit test; expect PASS.

### Task 2: 原标注覆盖服务与管理员 API

**Files:**
- Modify: `potato/potato/direct_audio_review.py`
- Modify: `potato/potato/routes.py`
- Create: `potato/tests/server/test_direct_audio_review_api.py`

**Interfaces:**
- Produces: `GET /adjudicate/api/audio-reviews`
- Produces: `POST /adjudicate/api/audio-reviews/claim`
- Produces: `PUT /adjudicate/api/audio-reviews/<recording_id>/<annotator>`
- Produces: `POST /adjudicate/api/audio-reviews/<recording_id>/<annotator>/complete`
- Produces: `POST /adjudicate/api/audio-reviews/<recording_id>/<annotator>/reopen`

- [ ] Write integration tests that seed a real saved audio annotation, verify one-annotation queue eligibility and non-admin 403, claim ownership, validation, direct UserState overwrite, readable JSON sync, snapshot creation, completion and reopen.
- [ ] Run the new server test; expect 404 failures.
- [ ] Add administrator-gated routes and register them in `configure_routes`; validate segment numbers and sort by start time before saving.
- [ ] Re-run the server test; expect PASS.

### Task 3: ASR 专用审核界面

**Files:**
- Modify: `potato/potato/templates/adjudication.html`
- Create: `potato/potato/static/direct-audio-review.js`
- Modify: `potato/potato/static/adjudication.css`
- Modify: `potato/examples/audio/asr-transcript-correction/config.yaml`
- Modify: `potato/tests/server/test_direct_audio_review_api.py`

**Interfaces:**
- Consumes: Task 2 API
- Produces: 待审核/审核中/已完成列表、领取按钮、音频播放器、片段编辑表、保存修改、审核通过和重新编辑按钮

- [ ] Add failing page assertions for the Chinese controls and dedicated script.
- [ ] Run focused test; expect missing-control failures.
- [ ] Add `adjudication.direct_edit_audio_annotations: true`, pass it to the template, and render the dedicated UI only when enabled; keep existing generic markup/scripts otherwise.
- [ ] Implement fetch/render/edit/button state logic with escaped text and Chinese errors.
- [ ] Re-run focused tests; expect PASS.

### Task 4: 导出审核状态

**Files:**
- Modify: `potato/potato/admin_annotation_data.py`
- Modify: `potato/tests/server/test_admin_annotation_data.py`
- Modify: `potato/tests/server/test_direct_audio_review_api.py`

**Interfaces:**
- Extends each annotation record with `review_status`, `reviewed_by`, `reviewed_at`
- JSON and SQLite exporters include the three fields

- [ ] Write failing JSON and SQLite assertions for pending and completed review metadata.
- [ ] Run focused export tests; expect missing fields/columns.
- [ ] Enrich records from `DirectAudioReviewStore` and migrate SQLite schema generation.
- [ ] Re-run focused tests; expect PASS.

### Task 5: 回归与本地验收

**Files:**
- No production changes expected

**Interfaces:**
- Produces: verification evidence and a running local service

- [ ] Run direct-review, admin-data, ASR workflow, adjudication demo and admin dashboard tests.
- [ ] Restart port 8012 with the current ASR config.
- [ ] Verify the real admin session sees a user2 review task, can claim it, and UI fields render without mutating data during the smoke test.
- [ ] Restore generated layout/template artifacts, run `git diff --check`, and inspect the final diff without touching `flask_server.py`.
