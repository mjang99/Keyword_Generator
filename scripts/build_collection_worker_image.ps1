param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryUrl,
    [string]$Tag = "latest",
    [string]$Region = "ap-northeast-2",
    [string]$Platform = "linux/amd64",
    [switch]$Push
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$dockerfile = Join-Path $repoRoot "docker\collection-worker\Dockerfile"
$imageUri = "${RepositoryUrl}:${Tag}"
$registry = $RepositoryUrl.Substring(0, $RepositoryUrl.LastIndexOf("/"))

Push-Location $repoRoot
try {
    if ($Push) {
        aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
        docker buildx build `
            --platform $Platform `
            --provenance=false `
            --sbom=false `
            -f $dockerfile `
            -t $imageUri `
            --push `
            .
    }
    else {
        docker buildx build `
            --platform $Platform `
            --provenance=false `
            --sbom=false `
            -f $dockerfile `
            -t $imageUri `
            --load `
            .
    }
}
finally {
    Pop-Location
}

Write-Output $imageUri
