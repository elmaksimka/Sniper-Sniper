$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".env.local")) {
    Write-Host "Alpha Engine has no local environment to stop."
    exit 0
}

docker compose --env-file .env.local -f docker-compose.local.yml down
if ($LASTEXITCODE -ne 0) {
    throw "Local Alpha Engine shutdown failed."
}

Write-Host "Alpha Engine stopped. Its PostgreSQL volume was preserved."
