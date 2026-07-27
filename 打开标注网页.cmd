@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0potato"
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "CONFIG_FILE=%PROJECT_DIR%\examples\audio\asr-transcript-correction\config.yaml"
set "WEB_URL=http://127.0.0.1:8012/"

if not exist "%PYTHON_EXE%" (
    echo 首次运行：正在创建本地 Python 环境……
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv "%PROJECT_DIR%\.venv"
    ) else (
        where python >nul 2>&1
        if errorlevel 1 (
            echo 未检测到 Python 3。请先安装 Python 3.11 或更高版本。
            pause
            exit /b 1
        )
        python -m venv "%PROJECT_DIR%\.venv"
    )

    if not exist "%PYTHON_EXE%" (
        echo 创建 Python 环境失败。
        pause
        exit /b 1
    )

    echo 正在安装网页运行所需的核心依赖，首次运行可能需要几分钟……
    "%PYTHON_EXE%" -m pip install "%PROJECT_DIR%"
    if errorlevel 1 (
        echo 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%WEB_URL%'; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1"
if errorlevel 1 (
    start "Potato annotation server" /min /D "%PROJECT_DIR%" "%PYTHON_EXE%" -m potato.flask_server start "%CONFIG_FILE%" -p 8012
)

for /L %%I in (1,1,60) do (
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%WEB_URL%'; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1"
    if not errorlevel 1 (
        start "" "%WEB_URL%"
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)

echo 网页未能在 60 秒内启动，请查看最小化的服务窗口中的错误信息。
pause
exit /b 1
