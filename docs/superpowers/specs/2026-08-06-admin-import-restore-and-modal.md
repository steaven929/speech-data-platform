# 管理员批量导入修复与提示（功能 6）

## 背景与根因
`85590c5` 提交在重构 routes.py 时删除了批量导入的两个后端接口（`/admin/api/audio-import/preview`、`/confirm`）及其配套代码，导致管理后台"批量导入"页无法使用（实测返回 404，前端解析 JSON 失败仅显示"校验失败"）。`admin_audio_import.py` 的解析/预览/原子写入逻辑本身完好，仅缺少路由接线。

## 修改范围
- `potato/potato/routes.py`：
  - 恢复 `shutil`、`tempfile`、`threading`、`pathlib.Path`、`werkzeug.utils.secure_filename` 导入。
  - 恢复批次暂存状态 `_audio_import_batches`、锁、限额（200 个文件 / 2GB / token 30 分钟 TTL）。
  - 恢复 `_audio_import_task_path`、`_audio_import_data_file`、`_cleanup_expired_audio_imports`、`_fill_and_persist_coverage_assignments`。
  - 恢复 `admin_audio_import_preview` / `admin_audio_import_confirm` 两个路由及 `add_url_rule` 注册。
- `potato/potato/templates/admin.html`：
  - 新增成功/失败弹窗（自定义 modal）：校验通过、校验未通过（逐条列出重复/格式错误/无对应记录/缺少音频）、导入成功、导入失败。
  - 确认导入改用原生 fetch 以读取后端错误信息。

## 不改动
- `admin_audio_import.py` 解析/预览/提交逻辑。
- 已有数据、音频、任务与标注。

# 功能 7：校验与字段调整
- 转写列兼容读取「阿里转译」「预转写」「转写」任一列名。
- 「类别」列不强制：Excel 无该列或为空时，导入自动写入默认标签「未分类」；有则读取其值。
- 每条任务写入 `category` 字段；实例列表 API 返回 `category`。
- 首列行号列继续忽略。

# 功能 8：精简实例列表列
- 保留：编号、类别、完成度%、标注员（仅人名，不显示 n/3）。
- 删除：文本预览、标注数、最多标签、分歧、平均耗时、AI 实例数。
- 恢复 `admin_api_instances` 的覆盖率补充逻辑（`assigned_annotators`/`assignment_target`/`summary` 短肋数据），支撑标注员列显示。

# 功能 9：实例页按「类别」筛选
- 后端 `potato/admin.py`：`InstanceData` 新增 `category` 字段；`get_instances_data` 新增 `filter_category` 参数（精确匹配；缺失/空类别统一视为「未分类」）；响应新增 `categories` 列表（全部去重类别，供前端下拉）。
- 后端 `potato/routes.py`：`/admin/api/instances` 读取并透传 `filter_category` 查询参数。
- 前端 `potato/templates/admin.html`：实例 tab 的 table-controls 新增「全部分类」下拉（样式与「全部实例」等一致）；`loadInstances()` 读取选中类别并以 `filter_category` 传参；`displayInstances()` 用响应 `categories` 动态填充选项并保持当前选中。
- 已验证：无过滤 25 条；`filter_category=未分类` → 25 条；不存在类别 → 0 条。

# 功能 9 补充：批量导入界面手动设置标签（类别）
- 前端「批量导入」tab 新增「设置标签（类别，选填）」输入框；校验预览时随 multipart 一起提交 `category` 字段。
- 后端 `routes.py` 预览接口读取 `category`，调用 `admin_audio_import.apply_category_override` 覆盖该批次所有行的类别（优先级高于 Excel「类别」列）。
- 输入为空时保持原逻辑：读 Excel「类别」列，无则归「未分类」。
- 校验通过弹窗提示实际使用的标签；修改标签需重新校验预览。
- 已验证：预览接口传 `category=质检专项` 后批次所有行 category 均被覆盖；空值保持原类别。

# 功能 9 补充：实例页直接修改录音类别
- 后端 `routes.py` 新增 `POST /admin/api/instances/<instance_id>/category`（`Permission.VIEW_ADMIN_DASHBOARD` 鉴权）：更新 ItemStateManager 内存数据 + 原子写回 items.json（临时文件 + `os.replace`），空值归一为「未分类」；已在 `configure_routes` 注册 URL 规则。
- 前端 `admin.html` 实例列表「类别」列改为内联下拉（选项来自接口 `categories` + 当前值），`onchange` 调 `updateInstanceCategory()` 保存，成功/失败弹窗提示，随后刷新列表。
- 已验证：真实服务修改 `20260720151906185` 类别 → 接口返回成功、类别筛选即时生效、items.json 持久化，随后恢复为「未分类」。

# 功能 10：批量分配（预计算 + 人工确认）
- 后端 `routes.py` 新增 `POST /admin/api/assignment/batch`（`Permission.VIEW_ADMIN_DASHBOARD` 鉴权，已注册 configure_routes）：
  - `dry_run=true`：`_build_assignment_plan()` 纯计算（不落库）——按每条录音缺口补到 `target_per_item`（默认 3），候选标注员按「名下任务最少者优先」均衡分配，已分配的不重复，容量不足/无人可补记入 `unfulfilled` 警告。
  - `dry_run=false`：按（可微调的）`plan` 校验后真正 `assign_instance` 并 `save_user_state`；校验每人不超配额、每条不超过目标。
- 前端 `admin.html` 实例页新增「批量分配」按钮 + 两步弹窗：
  - 第一步：圈定方式二选一（按当前筛选范围全部 / 随机抽取 N 条）、标注员多选（默认排除配额 0）、目标人数（默认 3）。
  - 第二步：生成预览（概览每人新增数 + 明细表，每条可勾选微调建议标注员）→ 确认分配 → 结果弹窗并刷新列表。
- 已验证：dry-run 生成方案正确（已有标注员跳过、均衡分配、容量不足提示）；confirm 应用微调方案、容量校验拒绝超额；真实服务 26 条 dry-run + 无副作用 confirm 通过；单元测试 11 通过（2 个既有 config 相关失败）。
