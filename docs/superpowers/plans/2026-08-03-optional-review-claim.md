# Optional Review Claim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow administrators to edit, save, and complete pending reviews without claiming them first, while retaining optional claiming as a multi-admin lock.

**Architecture:** Extend the review-state authorization rule so an unassigned pending record is writable by the current administrator and becomes attributed to that administrator when completed. Keep assigned records writable only by their owner. Mirror the rule in the browser controls.

**Tech Stack:** Python, Flask, pytest, vanilla JavaScript

## Global Constraints

- Saving continues to overwrite the annotator's original data and create a pre-change snapshot.
- Records assigned to another administrator remain read-only.
- Claiming remains available and changes the status to `in_progress`.

---

### Task 1: Pending review API authorization

**Files:**
- Modify: `potato/tests/server/test_direct_audio_review_api.py`
- Modify: `potato/potato/direct_audio_review.py`
- Modify: `potato/potato/routes.py`

**Interfaces:**
- Consumes: `DirectAudioReviewStore.get()`, `record_snapshot()`, `complete()`
- Produces: pending records accepted by update and complete endpoints; completion attributes the current admin

- [ ] **Step 1: Write failing integration tests**

Add tests that PUT modified segments and POST complete while the record is still `pending`, then assert the original annotation changed, the snapshot exists, and `reviewed_by == "admin"`.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m pytest tests/server/test_direct_audio_review_api.py -q`

Expected: update/complete returns a conflict because the pending record has no owner.

- [ ] **Step 3: Implement the minimal authorization change**

Permit mutation when state is `pending` and `assigned_to` is empty. Continue rejecting a record assigned to a different administrator. On direct completion, set the reviewer and completion timestamp without requiring a prior claim.

- [ ] **Step 4: Run focused tests and verify pass**

Run: `python -m pytest tests/server/test_direct_audio_review_api.py -q`

Expected: PASS.

### Task 2: Pending review page controls

**Files:**
- Modify: `potato/tests/server/test_direct_audio_review_api.py`
- Modify: `potato/potato/static/direct-audio-review.js`

**Interfaces:**
- Consumes: `window.DIRECT_REVIEW_ADMIN`, queue item `review_status` and `assigned_to`
- Produces: enabled pending editors plus visible save, complete, and optional claim buttons

- [ ] **Step 1: Add a failing source/UI assertion**

Assert that the page script treats `pending` records with no assignee as editable.

- [ ] **Step 2: Run the UI test and verify failure**

Run: `python -m pytest tests/server/test_direct_audio_review_api.py::test_asr_adjudication_page_has_direct_edit_controls -q`

Expected: FAIL because editability currently requires `in_progress` ownership.

- [ ] **Step 3: Update browser state rules**

Set `editable` when the record is unassigned and pending, or when it is in progress and owned by the current administrator. Leave claim visible only for pending records.

- [ ] **Step 4: Run focused and regression tests**

Run: `python -m pytest tests/unit/test_direct_audio_review.py tests/server/test_direct_audio_review_api.py tests/server/test_admin_annotation_data.py tests/server/test_asr_admin_workflow.py -q`

Expected: PASS.

### Task 3: Live verification

**Files:**
- No source changes

**Interfaces:**
- Consumes: running server on port 8012
- Produces: verified pending edit controls and unchanged queue data

- [ ] **Step 1: Run syntax and whitespace checks**

Run: `node --check potato/potato/static/direct-audio-review.js` and `git diff --check`.

- [ ] **Step 2: Restart the application**

Start the ASR config on `127.0.0.1:8012`.

- [ ] **Step 3: Verify the rendered page**

Log in as the administrator and confirm pending records render `分配给自己`, `保存修改`, and `审核通过` without performing a write.
