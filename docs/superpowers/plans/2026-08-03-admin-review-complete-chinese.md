# Admin and Review Complete Chinese UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate all user-visible text in the currently used management dashboard and direct audio review page into Chinese.

**Architecture:** Keep existing i18n keys and behavior unchanged, replace remaining hard-coded English UI strings with Chinese, and add rendered-page regression assertions for the known omissions. Product names and technical abbreviations remain unchanged.

**Tech Stack:** Jinja2, vanilla JavaScript, Flask, pytest

## Global Constraints

- Preserve `Prolific`, `MTurk`, `HIT ID`, `API`, `JSON`, and `SQLite`.
- Do not change API payload keys or application logic.
- Cover menus, headings, cards, tables, empty states, loading states, notifications, and errors.

---

### Task 1: Add localization regression coverage

**Files:**
- Modify: `potato/tests/server/test_asr_admin_workflow.py`

- [ ] Add assertions that rendered admin and adjudication pages contain the expected Chinese controls and exclude known English UI labels.
- [ ] Run the focused tests and verify they fail on the current English labels.

### Task 2: Translate dashboard UI strings

**Files:**
- Modify: `potato/potato/templates/admin.html`

- [ ] Translate visible strings in Questions, Behavioral Analytics, Devices, Crowdsourcing, Configuration, and optional analytics panels.
- [ ] Preserve product names and technical abbreviations.
- [ ] Run focused tests and verify they pass.

### Task 3: Audit direct review and live pages

**Files:**
- Modify only if omissions are found: `potato/potato/templates/adjudication.html`, `potato/potato/static/direct-audio-review.js`

- [ ] Scan the rendered pages for remaining visible English text.
- [ ] Run related regression tests and JavaScript syntax checks.
- [ ] Restart port 8012 and inspect every relevant dashboard tab plus the direct review page.
