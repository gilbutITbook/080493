# =============================================
# stop_agents.ps1 — 모든 에이전트 서버 종료 스크립트
# =============================================
# 사용법: .\stop_agents.ps1

Write-Host "Stopping agent servers..." -ForegroundColor Yellow

# agents.pid 파일에서 프로세스 정보 읽기
if (Test-Path "agents.pid") {
    $agents = Get-Content "agents.pid" | ConvertFrom-Json
    foreach ($agent in $agents) {
        $processId = $agent.Process.Id
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "[Stopped] $($agent.Name) (PID: $processId)" -ForegroundColor Green
        }
    }
    Remove-Item "agents.pid" -ErrorAction SilentlyContinue
}

# 포트별로 프로세스 종료 (백업 방법) 
$ports = @(6101, 6102, 6103, 6104, 6105, 6106, 6107)
foreach ($port in $ports) {
    $processes = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | 
        Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processes) {
        if ($processId) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "[Stopped] Process on port $port (PID: $processId)" -ForegroundColor Gray
        }
    }
}

Write-Host "All agent servers stopped." -ForegroundColor Green

