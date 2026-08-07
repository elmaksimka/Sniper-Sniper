$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath ".env.local")) {
    Copy-Item -LiteralPath ".env.local.example" -Destination ".env.local"
    Write-Host "Created .env.local from the free local defaults."
}

docker compose --env-file .env.local -f docker-compose.local.yml up -d --build
if ($LASTEXITCODE -ne 0) {
    throw "Local Alpha Engine startup failed."
}

docker compose --env-file .env.local -f docker-compose.local.yml ps
if ($LASTEXITCODE -ne 0) {
    throw "Could not read local Alpha Engine status."
}

Write-Host "Alpha Engine is starting at http://127.0.0.1:8000/docs"
