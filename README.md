# 面向语音AI模型训练的数据预处理平台

这是一个面向语音 AI 模型训练场景的数据预处理平台。项目支持管理员批量导入音频和初始转写，按批次给标注员分发任务，收集多人标注结果，并在管理后台完成审核、修订和导出。

这个仓库是脱敏后的公开展示版本，适合作为语音数据标注、任务分发、人工审核和结果导出流程的工程实践案例。

## 核心功能

- 批量导入音频：支持 Excel 或 JSON 转写清单与 WAV 音频一并导入。
- 导入批次管理：每批数据自动生成批次标识，便于后续筛选和分配。
- 标注员账号体系：管理员和标注员分角色登录。
- 任务分发：管理员按批次、分类和配额将录音分配给不同标注员。
- 音频标注：标注员可在波形和片段列表中校正时间段、角色和转写文本。
- 多人交叉标注：支持每条录音分配给至少 N 个标注员。
- 审核工作台：管理员可查看标注结果、直接修改标注员原始结果并保留快照。
- 结果导出：支持导出 JSON 和 SQLite，导出文件名自动带时间戳。
- 本地化界面：当前主要使用流程已中文化。

## 技术栈

- Python 3.9+
- Flask
- YAML 配置驱动
- JSON/SQLite 数据存储
- 原生 HTML/CSS/JavaScript

## 快速启动

进入项目目录：

```bash
cd potato
```

安装依赖：

```bash
python -m pip install -e .
python -m pip install xlrd pytest
```

准备示例数据：

```bash
mkdir -p examples/audio/asr-transcript-correction/data
cp examples/audio/asr-transcript-correction/items.example.json \
   examples/audio/asr-transcript-correction/data/items.json
cp examples/audio/asr-transcript-correction/users.example.jsonl \
   examples/audio/asr-transcript-correction/users.jsonl
```

启动服务：

```bash
PYTHONPATH=. python -m potato.flask_server start \
  examples/audio/asr-transcript-correction/config.yaml \
  -p 8013
```

访问：

```text
http://127.0.0.1:8013/
```

示例账号：

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 管理员 | admin | 123 |
| 标注员 | annotator_a | 123 |
| 标注员 | annotator_b | 123 |
| 标注员 | annotator_c | 123 |

## 典型流程

1. 管理员登录后台。
2. 在“批量导入”中选择 Excel 或 JSON 转写清单，并上传对应 WAV 音频。
3. 在“实例”页面按导入批次筛选录音。
4. 设置每条录音需要的标注人数和标注员配额。
5. 批量分配任务。
6. 标注员登录并完成音频转写校对。
7. 管理员在审核页面查看、修改、通过结果。
8. 在管理后台导出 JSON 或 SQLite。

## 示例 JSON 导入格式

```json
[
  {
    "id": "demo_audio_001",
    "audio_url": "/media/demo_audio_001.wav",
    "transcript": "您好，请问有什么可以帮您？\n\n我想咨询一下业务办理流程。",
    "category": "示例分类"
  }
]
```

导入时需要同时上传与 `audio_url` 或 `id` 对应的 WAV 文件。

## 隐私与数据说明

公开版本不包含真实录音、真实转写文本、真实标注结果、数据库、密钥或本地账号配置。以下内容默认不应提交：

- `media/`
- `annotation_output/`
- `waveform_cache/`
- `project.sqlite*`
- `admin_api_key.txt`
- `data/items.json`
- 真实 Excel / JSON / 音频文件

## 许可与致谢

本项目遵循 GPL-3.0-or-later 许可证发布。

项目开发过程中参考并复用了开源社区中的部分通用数据标注能力，相关第三方版权、许可和致谢信息见 [NOTICE.md](NOTICE.md)。
