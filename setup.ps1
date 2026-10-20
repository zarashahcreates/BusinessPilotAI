# One-time setup for Windows PowerShell:  .\setup.ps1
$ErrorActionPreference = "Stop"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path ".env")) { Copy-Item .env.example .env; Write-Host "Created .env (add your OPENAI_API_KEY there if you want AI commentary)." }
Write-Host "Done. Start the app with:  .\.venv\Scripts\python.exe -m streamlit run app.py"
