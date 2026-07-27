Potato 靖江热线 ASR 标注交付包（15 条全新任务）

本包包含：
- 表格中连续的第 36–50 条靖江热线录音，共 15 个标注条目
- 起始录音：20260720151906185.wav
- 结束录音：20260720153426286.wav
- 对应的阿里 ASR 初始转写内容
- Potato 完整源码和依赖清单

原包中的录音、用户进度、历史标注、可读标注导出和项目数据库均已删除。
本包首次打开时，15 条任务全部处于“未标注”状态。

一、开始标注（Windows）
1. 解压整个压缩包，不能只打开压缩包内的文件。
2. 双击“打开标注网页.cmd”。
3. 首次运行若没有本地 Python 环境，脚本会自动创建并安装依赖，需要联网并等待数分钟。
4. 浏览器打开 http://127.0.0.1:8012/ 后，输入任意用户名即可进入标注。
5. 请保持最小化的“Potato annotation server”窗口开启；关闭该窗口会停止网页服务，但已保存标注不会丢失。

系统要求：
- Windows 10/11
- Python 3.11 或更高版本
- 首次安装依赖时可访问互联网

二、数据位置
- 录音：potato\examples\audio\asr-transcript-correction\media\
- 15 条初始任务：potato\examples\audio\asr-transcript-correction\data\items.json
- 新标注保存目录：potato\examples\audio\asr-transcript-correction\annotation_output\

三、重复录音说明
表格第 43–44 条和第 49–50 条分别是两组重复地址。为了严格保留连续 15 条记录，
本包将第二份录音保存为带行号后缀的独立文件，并使用独立任务 ID，不会被网页去重。

注意：
- Potato 会在切换或提交任务时自动保存。
- 如果 8012 端口被占用，可编辑“打开标注网页.cmd”，把其中的 8012 改成其他端口。
