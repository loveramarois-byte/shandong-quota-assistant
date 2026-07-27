@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"
set "PYTHON=%PROJECT_ROOT%.venv\Scripts\pythonw.exe"
if not exist "%PYTHON%" goto missing_python
if not exist "%PROJECT_ROOT%run.py" goto missing_entry
if defined SHANDONG_QUOTA_DB goto launch
if exist "%PROJECT_ROOT%data\shandong_quota.sqlite" goto launch
goto missing_database

:launch
start "" "%PYTHON%" "%PROJECT_ROOT%run.py"
goto :eof

:missing_python
echo [ERROR] Missing .venv\Scripts\pythonw.exe
exit /b 1

:missing_entry
echo [ERROR] Missing run.py
exit /b 1

:missing_database
echo [ERROR] Missing data\shandong_quota.sqlite
exit /b 1
