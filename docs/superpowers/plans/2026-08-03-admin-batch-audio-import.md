# Admin Batch Audio Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Chinese admin workflow that previews and atomically imports the existing legacy XLS transcript format with matching WAV files.

**Architecture:** Put parsing and file persistence in a focused service module, expose preview/confirm admin APIs from the existing Flask routes, and add one new admin tab. Confirmed imports append to `items.json` and call `ItemStateManager.add_item()` so they are usable without restart.

**Tech Stack:** Flask, xlrd, Python standard-library `wave`, pytest, vanilla HTML/JavaScript.

## Global Constraints

- Parse the existing columns `录音地址` and `阿里转译` from `.xls`.
- Match audio by basename from `录音地址`; accept WAV only in the first version.
- Never overwrite existing audio, items, assignments, or annotations.
- Validate the complete batch before writing and keep imported data git-ignored.

---

### Task 1: Legacy XLS parser and item builder

**Files:**
- Create: `potato/admin_audio_import.py`
- Test: `tests/unit/test_admin_audio_import.py`
- Modify: `setup.py`, `requirements.txt`

**Interfaces:**
- Produces: `parse_legacy_xls(path) -> list[TranscriptRow]`
- Produces: `build_audio_item(row, audio_path, media_url) -> dict`

- [ ] Write tests proving column lookup, URL basename matching, blank-line segmentation, alternating speakers, continuous proportional WAV timings, and malformed-row errors.
- [ ] Run the focused test and verify it fails because the module is absent.
- [ ] Implement the smallest parser/item builder and add `xlrd>=2.0.1` to dependencies.
- [ ] Run the focused tests and verify they pass.

### Task 2: Atomic preview and confirm service

**Files:**
- Modify: `potato/admin_audio_import.py`
- Test: `tests/unit/test_admin_audio_import.py`

**Interfaces:**
- Produces: `preview_import(xls_path, audio_paths, existing_ids, media_dir) -> ImportPreview`
- Produces: `commit_import(preview, data_file, media_dir, item_manager) -> list[dict]`

- [ ] Write failing tests for duplicate IDs, missing/mismatched WAVs, unchanged files on validation failure, atomic JSON append, and runtime item registration.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Implement validation, staged file copies, atomic JSON replacement, and runtime registration.
- [ ] Run focused tests and verify they pass.

### Task 3: Admin APIs

**Files:**
- Modify: `potato/routes.py`
- Test: `tests/server/test_admin_audio_import.py`

**Interfaces:**
- Produces: `POST /admin/api/audio-import/preview`
- Produces: `POST /admin/api/audio-import/confirm`

- [ ] Write failing Flask tests for admin authorization, multipart validation, preview token handling, and successful confirmation.
- [ ] Run the route tests and confirm expected failures.
- [ ] Add the two guarded routes and server-side temporary upload storage.
- [ ] Run route tests and verify they pass.

### Task 4: Chinese admin interface

**Files:**
- Modify: `potato/templates/admin.html`
- Test: `tests/unit/test_admin_template_localization.py`

**Interfaces:**
- Consumes: preview and confirm APIs from Task 3.
- Produces: `批量导入` admin tab with file pickers, validation summary, and confirm action.

- [ ] Add a failing template test for the tab, accepted file types, preview table, and Chinese status copy.
- [ ] Run the template test and confirm it fails.
- [ ] Add the tab and JavaScript workflow with buttons disabled during requests.
- [ ] Run template and focused feature tests.

### Task 5: End-to-end verification

**Files:**
- No production files expected.

- [ ] Run all focused tests and relevant existing admin tests.
- [ ] Start the ASR project, log in as administrator, preview a sample XLS/WAV pair, cancel once, then import and verify the new item appears without restart.
- [ ] Confirm existing items and annotation exports remain unchanged except for the intentionally imported item.
