@echo off
REM Runs Sayso straight from the source code (with a console window for logs).
cd /d "%~dp0"
if not exist .venv (
  py -3.11 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python -m sayso
pause
