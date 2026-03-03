# =============================================
# Run all agents in background (stable version)
# =============================================

$python = "C:\Python313\python.exe"
$base   = "C:\Users\JYSEO\A2A\Generate_Proposal"

$logDir = "$base\logs"
if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$agents = @(
    @{ module="agents.competitor_agent"; port=6001; name="competitor" }
    @{ module="agents.customer_agent";   port=6002; name="customer" }
    @{ module="agents.feature_agent";    port=6003; name="feature" }
    @{ module="agents.revenue_agent";    port=6004; name="revenue" }
    @{ module="agents.formatter_agent";  port=6005; name="formatter" }
    @{ module="agents.markdown_writer";  port=6006; name="writer" }
)

Write-Host "Starting all agents in background..."

foreach ($a in $agents) {

    $log = "$logDir\$($a.name).log"
    # ❗ 로그 파일을 만지지 말 것. (삭제 또는 초기화 금지)

    $args = "-m $($a.module) --port $($a.port)"

    Start-Process -FilePath $python `
                  -ArgumentList $args `
                  -WorkingDirectory $base `
                  -WindowStyle Hidden `
                  -RedirectStandardOutput $log

    Write-Host "-> Started $($a.name) on port $($a.port)"
}

Write-Host "`nAll agents launched in background."
Write-Host "Logs: $logDir"
