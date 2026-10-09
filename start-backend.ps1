$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$activateScript = Join-Path $repoRoot ".venv\Scripts\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    throw "Virtual environment activation script was not found at $activateScript"
}

& $activateScript
Set-Location (Join-Path $repoRoot "backend")
python -m uvicorn main:app --host 127.0.0.1 --port 8000
