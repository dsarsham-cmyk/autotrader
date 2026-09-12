@echo off
rem Auto-start the Auto Trader (runs at login).
rem Primary strategy: range + momentum composite rotation on 3x ETFs.
rem See csmom_runner.py --leveraged --composite (top_k=3, weekly rebalance).
cd /d "%~dp0"
start "" .venv\Scripts\pythonw.exe csmom_runner.py --leveraged --composite
start "" .venv\Scripts\pythonw.exe dashboard.py
