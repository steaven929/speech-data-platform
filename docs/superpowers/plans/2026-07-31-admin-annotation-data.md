# 管理后台标注数据页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有管理后台查看已持久化的录音片段标注，并下载 JSON 或 SQLite 结果。

**Architecture:** 新建独立的标注结果读取与导出模块，把内部 `UserState` 转换成稳定记录；`routes.py` 只负责管理员鉴权和 HTTP 响应；`admin.html` 增加一个按需加载的中文标签页。SQLite 使用临时文件生成，现有 `project.sqlite` 不变。

**Tech Stack:** Python 3、Flask、SQLite、Jinja/原生 JavaScript、pytest/requests

## Global Constraints

- 仅展示已经持久化的用户标注，不把数据集预置片段算作已提交。
- 新增接口复用现有管理员会话或 `X-API-Key` 鉴权。
- JSON 和 SQLite 均不包含录音二进制。
- 不修改现有 `project.sqlite` 表结构。
- 当前 `flask_server.py` 的用户未提交改动不得覆盖。

---

### Task 1: 标注结果读取模块

**Files:**
- Create: `potato/potato/admin_annotation_data.py`
- Create: `potato/tests/server/test_admin_annotation_data.py`

**Interfaces:**
- Consumes: `UserStateManager.get_user_ids()`、`UserState.get_all_annotations()`
- Produces: `collect_audio_annotation_records(user_state_manager) -> list[dict]`
- Produces: `build_annotation_export_payload(records) -> dict`
- Produces: `write_annotation_sqlite(records, path) -> None`

- [ ] **Step 1: Write the failing tests**

用轻量真实状态对象构造一条 `transcript_segments:_data` 标注，断言输出包含录音编号、标注员、按开始时间排序的片段；再断言畸形 JSON 返回带 `parse_error` 的记录。断言 JSON 汇总数字正确，并用真实 SQLite 连接检查 `annotations`、`segments` 表和字段值。

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd potato && python -m pytest tests/server/test_admin_annotation_data.py -q`

Expected: FAIL because `potato.admin_annotation_data` does not exist.

- [ ] **Step 3: Implement the minimal module**

遍历所有用户已保存的标注，兼容 Label 对象和字符串键，识别 `_data` 音频标注，标准化片段字段并排序。JSON payload 使用 UTC ISO 时间。SQLite 建表并参数化插入。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd potato && python -m pytest tests/server/test_admin_annotation_data.py -q`

Expected: PASS.

### Task 2: 管理 API 与下载响应

**Files:**
- Modify: `potato/potato/routes.py`
- Modify: `potato/tests/server/test_asr_admin_workflow.py`

**Interfaces:**
- Consumes: Task 1 的三个公开函数
- Produces: `GET /admin/api/annotation-data`
- Produces: `GET /admin/api/annotation-data/export/json`
- Produces: `GET /admin/api/annotation-data/export/sqlite`

- [ ] **Step 1: Write failing integration tests**

用 `user2` 登录并向 `/updateinstance` 保存一条录音片段；断言管理员列表接口能读取文本和时间，普通标注员收到 403；断言 JSON 下载响应和 SQLite 下载文件内容正确。

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd potato && python -m pytest tests/server/test_asr_admin_workflow.py -q`

Expected: new route tests FAIL with 404.

- [ ] **Step 3: Add authenticated routes**

调用现有管理员鉴权，列表接口支持 `annotator`、`recording_id` 查询参数；两个下载接口设置中文友好的固定文件名和正确 MIME 类型；SQLite 响应结束后清理临时文件。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd potato && python -m pytest tests/server/test_asr_admin_workflow.py -q`

Expected: PASS.

### Task 3: 管理后台标注数据标签页

**Files:**
- Modify: `potato/potato/templates/admin.html`
- Modify: `potato/examples/audio/asr-transcript-correction/config.yaml`
- Modify: `potato/tests/server/test_asr_admin_workflow.py`

**Interfaces:**
- Consumes: `GET /admin/api/annotation-data` 和两个下载接口
- Produces: 管理后台“标注数据”标签页

- [ ] **Step 1: Write failing page assertions**

断言管理员页面包含“标注数据”导航、标注员筛选、录音编号筛选、详情表头、“导出 JSON”和“导出 SQLite”控件。

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd potato && python -m pytest tests/server/test_asr_admin_workflow.py -q`

Expected: new page assertions FAIL.

- [ ] **Step 3: Implement the tab**

沿用现有标签页样式增加筛选区、汇总、可展开录音记录和片段表；首次切换时读取接口，筛选变化时重新加载；下载按钮直接访问受管理员会话保护的下载地址。所有当前界面文字使用中文。

- [ ] **Step 4: Run focused tests**

Run: `cd potato && python -m pytest tests/server/test_admin_annotation_data.py tests/server/test_asr_admin_workflow.py -q`

Expected: PASS.

### Task 4: 回归与浏览器验收

**Files:**
- No production changes expected

**Interfaces:**
- Consumes: 完整功能
- Produces: 验证证据

- [ ] **Step 1: Run regression tests**

Run: `cd potato && python -m pytest tests/server/test_admin_dashboard.py tests/server/test_admin_dashboard_api.py tests/server/test_asr_admin_workflow.py tests/server/test_admin_annotation_data.py -q`

Expected: PASS.

- [ ] **Step 2: Restart the local ASR service**

保留用户状态启动当前配置，确认 `http://127.0.0.1:8012/admin` 可访问。

- [ ] **Step 3: Browser acceptance**

以管理员会话打开“标注数据”，验证空状态或现有记录、筛选、展开详情以及两个下载响应；确认普通标注员不能读取接口。

- [ ] **Step 4: Restore generated artifacts and inspect diff**

恢复服务运行时重新生成的布局/模板文件，仅保留本功能源码、测试和文档。
