@echo off
chcp 65001 >nul
setlocal

set "RESULT_DIR=%~dp0potato\examples\audio\asr-transcript-correction\annotation_output"

if not exist "%RESULT_DIR%" mkdir "%RESULT_DIR%"

start "" "%RESULT_DIR%"
exit /b 0
