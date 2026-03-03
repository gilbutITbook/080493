# =============================================
# start_agents.ps1 — 모든 에이전트 서버 실행 스크립트
# =============================================
# 사용법: .\start_agents.ps1
# 모든 에이전트를 백그라운드로 실행합니다.

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Agent Server Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 프로젝트 루트 디렉토리로 이동
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# 에이전트 프로세스 저장용
$agents = @()

# 에이전트 실행 함수
function Start-Agent {
    param(
        [string]$Name,
        [string]$Module,
        [int]$Port
    )
    
    Write-Host "[Starting] $Name (Port $Port)..." -ForegroundColor Yellow
    
    # 로그 파일 경로
    $logFile = Join-Path $scriptPath "logs\$Name.log"
    $errorFile = Join-Path $scriptPath "logs\$Name.error.log"
    
    # 백그라운드에서 실행 (창 숨김, 로그 파일로 리다이렉션)
    $process = Start-Process -FilePath "python" `
        -ArgumentList "-m", $Module `
        -WindowStyle Hidden `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError $errorFile `
        -PassThru
    
    $agents += @{
        Name = $Name
        Process = $process
        Port = $Port
    }
    
    Start-Sleep -Seconds 2
    Write-Host "[Completed] $Name (PID: $($process.Id))" -ForegroundColor Green
    
    return $process
}

# 로그 디렉토리 생성
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
    Write-Host "[Created] logs directory" -ForegroundColor Gray
}

# 모든 에이전트 서버 시작
Write-Host "`nStarting agent servers..." -ForegroundColor Cyan

Start-Agent -Name "Feature" -Module "agents.feature_engineer" -Port 6101
Start-Agent -Name "Predictor" -Module "agents.predictor" -Port 6102
Start-Agent -Name "Explainer" -Module "agents.explainer" -Port 6103
Start-Agent -Name "Collab" -Module "agents.recommender_collaborative" -Port 6104
Start-Agent -Name "Content" -Module "agents.recommender_content" -Port 6105
Start-Agent -Name "Hybrid" -Module "agents.hybrid_aggregator" -Port 6106
Start-Agent -Name "Similar" -Module "agents.similar_customers" -Port 6107

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "All agent servers started!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`nRunning agents:" -ForegroundColor Yellow
foreach ($agent in $agents) {
    Write-Host "  - $($agent.Name) (Port $($agent.Port), PID: $($agent.Process.Id))" -ForegroundColor White
}

Write-Host "`nLog files: logs\ directory" -ForegroundColor Gray
Write-Host "`nTo stop: Press Ctrl+C or run stop_agents.ps1" -ForegroundColor Yellow

# 프로세스 ID를 파일에 저장 (나중에 종료하기 위해)
$agents | ConvertTo-Json | Out-File -FilePath "agents.pid" -Encoding UTF8

Write-Host "`nAgent servers are running in background." -ForegroundColor Cyan
Write-Host "To stop: Run stop_agents.ps1" -ForegroundColor Yellow
Write-Host "`nCheck processes: Get-Process | Where-Object {$_.Id -in @($($agents.Process.Id -join ', '))}" -ForegroundColor Gray

