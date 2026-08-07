# Admin Import Restore & Modal — Implementation Plan

> 状态：功能 6 已完成并通过实测。功能 7-10 待确认后另立计划。

## Task 1：恢复 routes.py 导入接口
- 从 `4989ac6` 恢复被删代码（导入、常量、辅助函数、preview/confirm 路由、URL 注册）。
- 验证：`import potato.routes` 后 URL map 包含两个 audio-import 规则。

## Task 2：前端弹窗
- `admin.html` 增加 `#audioImportModal`、`showImportModal`/`closeImportModal`。
- 预览成功/失败、确认导入成功/失败均弹出提示，失败时列出原因。

## 验证
- 重启服务后实测：xls + 2 条未导入 wav → `can_confirm=true`、ready 正确、token 返回。
- confirm 无效 token → 返回"导入预览已失效，请重新预览"。
- 真实 confirm 写入未执行（避免未经确认修改项目数据）。

## Task 3：功能 7 字段调整
- `admin_audio_import.py`：`TranscriptRow` 增加 `category`；解析器兼容转写列名、类别列可选；`build_audio_item` 写入 `category`。
- `admin.py`：实例序列化增加 `category`。

## Task 4：功能 8 列表精简
- `admin.html`：实例表头改为 4 列（编号/类别/完成度/标注员）；`displayInstances` 同步。
- `routes.py`：恢复 `admin_api_instances` 覆盖率补充（标注员来源）。

## 验证
- 导入相关单测 11 过（2 个原有 config 失败与本次无关）。
- 实例 API 返回类别=未分类、标注员列表、覆盖率摘要。
- 无类别列的 xls 预览正常（can_confirm=true）。
