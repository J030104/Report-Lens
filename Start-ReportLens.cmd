@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Install first: python -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -e .
  pause
  exit /b 1
)
if not "%~1"=="" (
  ".venv\Scripts\python.exe" -m reportlens gui "%~1"
) else if exist "local.reportlens.json" (
  ".venv\Scripts\python.exe" -m reportlens gui --config local.reportlens.json
) else (
  ".venv\Scripts\python.exe" -m reportlens gui examples/public-demo/garden-review.reportlens
)
