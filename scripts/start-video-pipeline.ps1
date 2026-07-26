$ErrorActionPreference = 'Continue'

$repoRoot = 'C:\Users\song\Documents\GitHub\video_pipeline'
$dockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
$logDirectory = Join-Path $repoRoot 'logs'
$logPath = Join-Path $logDirectory 'pipeline-autostart.log'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

function Write-StartupLog([string]$message) {
    "$(Get-Date -Format s) $message" | Out-File -FilePath $logPath -Append -Encoding utf8
}

Write-StartupLog 'Video pipeline auto-start requested.'
if (Test-Path -LiteralPath $dockerDesktop) {
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
}

$ready = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 3
}

if (-not $ready) {
    Write-StartupLog 'Docker engine was not ready after 180 seconds.'
    exit 1
}

Set-Location -LiteralPath $repoRoot
& docker compose up -d
if ($LASTEXITCODE -eq 0) {
    Write-StartupLog 'Docker compose services started successfully.'
    exit 0
}

Write-StartupLog "docker compose up failed with exit code $LASTEXITCODE."
exit $LASTEXITCODE
