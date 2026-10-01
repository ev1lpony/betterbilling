@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
  if errorlevel 1 goto :failed
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
)
.venv\Scripts\python.exe -c "import PySide6, fpdf" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
)
.venv\Scripts\python.exe main.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo BetterBilling could not start. See the error above.
pause
exit /b 1
