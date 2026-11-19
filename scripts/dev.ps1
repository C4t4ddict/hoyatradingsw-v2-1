param([switch]$Check)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Python 3.12로 .venv를 만들고 requirements.txt를 설치하세요. docs/RUNTIME_OPERATIONS.md 참고'
}
& $projectPython scripts/doctor.py
if ($LASTEXITCODE -ne 0) { throw '환경 진단 실패' }
if ($Check) { exit 0 }
$listeners = Get-NetTCPConnection -State Listen -LocalPort 8010,3001 -ErrorAction SilentlyContinue
if ($listeners) { throw '8010/3001 포트가 사용 중입니다. 기존 실행을 종료하거나 개별 실행 명령을 사용하세요.' }
$node = (Get-Command node -ErrorAction Stop).Source
$children = @()
try {
    $backend = Start-Process -FilePath $projectPython -ArgumentList '-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010' -WindowStyle Hidden -PassThru
    $children += $backend
    $web = Start-Process -FilePath $node -WorkingDirectory (Join-Path $projectRoot 'frontend') -ArgumentList 'node_modules/next/dist/bin/next dev -p 3001' -WindowStyle Hidden -PassThru
    $children += $web
    $collector = Start-Process -FilePath $projectPython -ArgumentList 'run_runtime.py' -WindowStyle Hidden -PassThru
    $children += $collector
    Write-Host '웹 http://127.0.0.1:3001 | API http://127.0.0.1:8010 | Ctrl+C로 종료'
    while (-not $backend.HasExited -and -not $web.HasExited) {
        Start-Sleep -Seconds 5
        if ($collector.HasExited) {
            Start-Sleep -Seconds 10
            $collector = Start-Process -FilePath $projectPython -ArgumentList 'run_runtime.py' -WindowStyle Hidden -PassThru
            $children += $collector
        }
    }
} finally {
    foreach ($child in $children) {
        if (-not $child.HasExited) { Stop-Process -Id $child.Id -ErrorAction SilentlyContinue }
    }
}
