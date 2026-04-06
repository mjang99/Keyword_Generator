$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv-dev\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Missing test environment: $pythonExe"
}

Push-Location $repoRoot
try {
    & $pythonExe -m pytest tests -q
}
finally {
    Pop-Location
}
