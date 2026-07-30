# Potato 标注平台

Potato 是一个基于 Python 和 Flask 的开源数据标注平台。项目通过 YAML 文件配置标注任务，无需修改业务代码即可创建文本分类、跨度标注、多媒体标注、问卷和模型输出评测等任务。

## 主要功能

- 使用 YAML 配置数据源、标注界面、用户和任务分配策略
- 支持文本、图片、音频、视频和文档等数据
- 支持单选、多选、量表、文本输入、跨度标注等多种标注方式
- 支持多用户协作、任务分配、质量控制和结果导出
- 提供可直接运行的示例项目
- 可通过浏览器访问，适合本地使用或部署到服务器

## 环境要求

- Python 3.8 或更高版本
- Git
- pip 和 Python 虚拟环境模块 `venv`
- 建议至少预留 512 MB 内存

## 快速开始

如果只需要使用 Potato，可通过 PyPI 安装：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install potato-annotation
potato start /path/to/config.yaml -p 8000
```

以上命令适用于 Linux 和 macOS。Windows 用户请使用下一节中的 PowerShell 命令。通过 PyPI 安装时不包含仓库中的 `examples/` 目录，需要使用自己的配置文件。

## 在 Windows 上安装

以下命令适用于 Windows PowerShell。请先安装 [Python](https://www.python.org/downloads/windows/) 和 [Git](https://git-scm.com/download/win)，并在安装时将它们加入 `PATH`。

```powershell
git clone https://github.com/steaven929/potato.git
Set-Location potato

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .

potato start examples/classification/single-choice/config.yaml -p 8000
```

如果 PowerShell 阻止虚拟环境激活脚本，可仅对当前窗口临时放行后重试：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

启动成功后，在浏览器中访问 [http://localhost:8000](http://localhost:8000)。按 `Ctrl+C` 可停止服务。

## 在 Linux 上安装

以下步骤适用于 Ubuntu 和 Debian。其他 Linux 发行版请使用对应的软件包管理器安装 Python、pip、venv 和 Git。

```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv

git clone https://github.com/steaven929/potato.git
cd potato

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

potato start examples/classification/single-choice/config.yaml -p 8000
```

服务默认可在 [http://localhost:8000](http://localhost:8000) 访问。如果配置文件中指定了其他端口，或通过 `-p` 传入了其他端口，请使用相应端口。

也可以不使用命令行入口，直接从源码启动：

```bash
python potato/flask_server.py start examples/classification/single-choice/config.yaml -p 8000
```

## 在 Windows 中通过 WSL 安装

WSL 可以在 Windows 中提供完整的 Linux 环境。以下步骤使用默认的 Ubuntu 发行版。

1. 以管理员身份打开 PowerShell。首次安装 WSL 时运行：

   ```powershell
   wsl --install
   ```

   如果 WSL 已经存在但还没有 Ubuntu，请改用：

   ```powershell
   wsl --list --online
   wsl --install -d Ubuntu
   ```

   如果下载长时间停在 `0.0%`，可以绕过 Microsoft Store 下载：

   ```powershell
   wsl --install -d Ubuntu --web-download
   ```

2. 按系统提示重启电脑。从开始菜单打开 Ubuntu，等待初始化完成，然后创建 Linux 用户名和密码。输入密码时终端不会显示字符，这是正常现象。

3. 在 PowerShell 中确认 Ubuntu 正在使用 WSL 2：

   ```powershell
   wsl --list --verbose
   ```

4. 打开 Ubuntu 终端，安装并启动 Potato：

   ```bash
   sudo apt update
   sudo apt install -y git python3 python3-pip python3-venv

   git clone https://github.com/steaven929/potato.git
   cd potato

   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -e .

   potato start examples/classification/single-choice/config.yaml -p 8000
   ```

5. 在 Windows 浏览器中访问 [http://localhost:8000](http://localhost:8000)。

建议将项目克隆到 WSL 的 Linux 文件系统（例如 `~/potato`），不要长期从 `/mnt/c/` 中运行，以获得更好的文件读写性能。

WSL 的安装和排障命令可参考 [Microsoft WSL 安装文档](https://learn.microsoft.com/zh-cn/windows/wsl/install)。

> **仓库访问说明：** 如果 `steaven929/potato` 是私有仓库，使用 HTTPS 克隆前需要拥有相应的 GitHub 访问权限，并使用个人访问令牌或其他受支持的身份验证方式。不要把访问令牌写入 README 或提交到仓库。

## 配置自己的标注任务

一个最小任务通常包含配置文件、数据文件和输出目录：

```text
my-task/
├── config.yaml
├── data/
│   └── items.json
└── annotation_output/
```

配置文件负责指定任务目录、数据字段、标注方式、用户策略和输出位置。建议先复制 [`examples/`](examples/) 中与需求最接近的示例，再根据数据修改配置。完整入门说明见 [`docs/quick-start.md`](docs/quick-start.md)。

运行自己的任务：

```bash
potato start my-task/config.yaml -p 8000
```

标注结果会写入配置项 `output_annotation_dir` 指定的目录。请定期备份任务配置、原始数据和标注结果。

## 可选功能

源码安装时可按需启用额外依赖：

```bash
# AI 服务
python -m pip install -e ".[ai]"

# PDF、Word、Markdown 和电子表格支持
python -m pip install -e ".[formats]"

# 安装全部可选功能
python -m pip install -e ".[all]"
```

只有在任务需要时才安装可选功能。使用外部模型或 OAuth 服务时，请通过环境变量或本地配置提供密钥，不要把密钥提交到 Git 仓库。

## 开发与测试

```bash
python -m pip install -r requirements-test.txt
python -m pytest tests/unit -v
```

完整测试可能需要浏览器、模型或其他可选依赖。提交代码前，请至少运行与改动范围相关的测试。

## 常见问题

### 找不到 `potato` 命令

确认虚拟环境已经激活，并重新执行安装命令。

Linux 或 macOS：

```bash
source .venv/bin/activate
python -m pip install -e .
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### 端口已被占用

通过 `-p` 使用其他端口：

```bash
potato start examples/classification/single-choice/config.yaml -p 8080
```

### 外部设备无法访问服务

本地示例主要用于开发和验证。对局域网或公网提供服务时，还需要正确配置监听地址、防火墙、反向代理、HTTPS 和身份验证。不要在没有访问控制的情况下公开标注数据。

## 文档

- [快速入门](docs/quick-start.md)
- [配置说明](docs/configuration/configuration.md)
- [标注类型与模板](docs/annotation-types/schemas_and_templates.md)
- [数据导出](docs/data-export/export_formats.md)
- [部署说明](docs/deployment/)

## 许可证

本项目采用 [GNU General Public License v3.0 or later](LICENSE) 许可证。使用、修改或分发本项目时，请遵守许可证条款。

## 参考项目

Potato 最初由 [davidjurgens/potato](https://github.com/davidjurgens/potato) 开源维护。有关功能设计、论文和社区资源，可访问 [Potato 官方文档](https://www.potatoannotator.com/docs)。

