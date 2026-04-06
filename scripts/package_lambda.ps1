param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$buildDir = Join-Path $repoRoot "artifacts\lambda-packages"

if (-not $OutputPath) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputPath = Join-Path $buildDir "keyword-generator-$timestamp.zip"
}

$srcPath = Join-Path $repoRoot "src"

if (-not (Test-Path $srcPath)) {
    throw "Missing source directory: $srcPath"
}

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

if (Test-Path $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}

Push-Location $repoRoot
try {
    Compress-Archive -Path "src" -DestinationPath $OutputPath -CompressionLevel Optimal
}
finally {
    Pop-Location
}

Write-Output $OutputPath
