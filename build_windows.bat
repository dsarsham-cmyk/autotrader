@echo off
REM Build the Auto Trader Windows desktop app into a single .exe.
REM Run this from the autotrader folder. Output goes to dist\AutoTrader.exe
cd /d "%~dp0"

echo Building AutoTrader.exe ...
if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

%PYTHON% -m pip install -r requirements-desktop.txt
if errorlevel 1 exit /b 1

%PYTHON% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "AutoTrader" ^
  --icon assets\icon.ico ^
  --hidden-import webview.platforms.edgechromium ^
  --collect-all pywebview ^
  --collect-all clr_loader ^
  --collect-all pythonnet ^
  desktop_app.py

if errorlevel 1 exit /b 1

echo.
echo Done. The app is at dist\AutoTrader.exe
