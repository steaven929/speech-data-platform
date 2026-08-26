# 面向语音AI模型训练的数据预处理平台示例项目

这是公开版语音转写校对示例配置，展示管理员导入、任务分发、标注员校对、审核和导出的完整流程。

## 准备本地示例数据

公开仓库不包含真实录音。若只想查看配置结构，可直接阅读：

- `items.example.json`
- `users.example.jsonl`
- `config.yaml`

若要本地启动，需要准备 WAV 文件并复制示例数据：

```bash
mkdir -p data media
cp items.example.json data/items.json
cp users.example.jsonl users.jsonl
```

然后将本地测试音频放入 `media/`，并确保文件名与 `items.json` 中的 `audio_url` 对应，例如：

```text
media/demo_audio_001.wav
media/demo_audio_002.wav
```

## 示例账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 管理员 | admin | 123 |
| 标注员 | annotator_a | 123 |
| 标注员 | annotator_b | 123 |
| 标注员 | annotator_c | 123 |

公开演示密码仅用于本地测试，实际部署时请重新生成账号和密码。

## 运行流程

1. 管理员登录 `/admin`。
2. 在“批量导入音频和转写”中上传 Excel 或 JSON 转写清单，并同时上传对应 WAV 音频。
3. 在“实例”页面按导入批次筛选并批量分配任务。
4. 标注员登录 `/annotate` 完成转写校对。
5. 管理员打开 `/adjudicate` 审核、修改并通过结果。
6. 回到 `/admin` 导出 JSON 或 SQLite。

## 不应提交的本地文件

- `data/items.json`
- `media/`
- `annotation_output/`
- `waveform_cache/`
- `project.sqlite*`
- `admin_api_key.txt`
- 真实 Excel / JSON / WAV 文件
