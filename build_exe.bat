@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"
"%PROJECT_ROOT%.venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --onedir --name ShandongQuotaAssistant --add-data "assets;assets" --collect-all customtkinter --collect-all lottie run.py
echo.
echo Build complete: %PROJECT_ROOT%dist\ShandongQuotaAssistant\ShandongQuotaAssistant.exe
