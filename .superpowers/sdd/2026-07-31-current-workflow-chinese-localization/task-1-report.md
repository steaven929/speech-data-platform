# Task 1 report: active ASR page characterization

## Status

Complete. The requested page-level characterization tests were added and
verified in the TDD red phase. No production code was changed.

## Changes

- Added `potato/tests/server/test_asr_chinese_ui.py`.
- The module-scoped `asr_server` fixture copies the real ASR `config.yaml`,
  `users.jsonl`, data, and media into an isolated temporary task directory,
  then starts `FlaskTestServer` on a random test port.
- The tests use real authenticated sessions for `user2` and `admin`, and make
  requests to `/`, `/annotate`, `/admin`, and `/adjudicate`.
- Each page asserts required Chinese user-facing text and the absence of the
  primary English controls named in the task brief.

## Test command

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /private/tmp/asr-ui-test-venv/bin/python -m pytest tests/server/test_asr_chinese_ui.py -v
```

The temporary virtual environment contains only test/runtime dependencies and
is outside the repository.

## Failure output summary

The command completed with the expected red result: **4 failed, 1 warning in
13.45s**.

- Login page: missing `语音标注平台` (the page currently presents the task name
  instead).
- Annotation page: missing `标注说明`.
- Admin page: missing `管理后台`; it still renders `Admin Dashboard` and
  `Annotators`.
- Adjudication page: missing `审核`; it still renders `Adjudication`, `Queue`,
  `Pending`, `Done`, `Confidence`, `Skip`, and `Submit and continue`.

The sole warning was urllib3's LibreSSL compatibility warning from the
temporary test environment; it does not affect route responses or assertions.

## Self-review

- Tests exercise the real Flask routes, real ASR configuration, and real
  password-authenticated sessions; no route or template is mocked.
- Expectations are literal, user-visible Chinese terms derived from the
  localization design and task brief, so a regression to English fails at the
  page boundary.
- The fixture mirrors the established ASR workflow test setup and keeps
  copied runtime state outside the example task directory.
- No existing dirty production changes were modified.

## Concerns

- The normal sandbox disallows binding the helper's 9100--9999 test ports,
  causing `find_free_port()` to exhaust its retry range. The required run was
  therefore performed with approved unsandboxed localhost binding on a random
  port (9494). The existing service at port 8012 was never restarted, stopped,
  or requested.
- These are deliberately red characterization tests. Subsequent localization
  tasks must make them green and should retain the route-level assertions.
