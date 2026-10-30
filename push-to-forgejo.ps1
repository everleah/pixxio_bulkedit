# push-to-forgejo.ps1 - Image bauen und in die Forgejo-Registry pushen
#
#   .\push-to-forgejo.ps1                    # Tag "latest"
#   .\push-to-forgejo.ps1 -Tag 0.2.0         # bestimmter Tag
#   .\push-to-forgejo.ps1 -SkipBuild         # nur pushen (Image existiert lokal)

param(
    [string]$Registry = "git.claudiapps.de",
    [string]$Namespace = "hoerl-im",
    [string]$Image = "pixxio_bulkedit",
    [string]$Tag = "latest",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$FullImageName = "$Registry/$Namespace/$Image`:$Tag"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "pixx.io Bulk-Editor - Build und Push" -ForegroundColor Cyan
Write-Host "  Image: $FullImageName" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if (-not $SkipBuild) {
    Write-Host "Baue Image..." -ForegroundColor Yellow
    docker build -t $FullImageName .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Docker build failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "Image gebaut: $FullImageName" -ForegroundColor Green
}

Write-Host "Login an der Forgejo-Registry..." -ForegroundColor Yellow
docker login $Registry
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker login failed" -ForegroundColor Red
    exit 1
}

Write-Host "Push..." -ForegroundColor Yellow
docker push $FullImageName
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker push failed" -ForegroundColor Red
    exit 1
}

Write-Host "Fertig: $FullImageName" -ForegroundColor Green
