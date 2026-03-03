Write-Host "================================"
Write-Host "  Starting A2A agent servers..."
Write-Host "================================"

$agents = @(
    @{ name="Draft Agent";  script="agents/draft_agent.py";  port=6001 }
    @{ name="Critic Agent"; script="agents/critic_agent.py"; port=6002 }
    @{ name="Scoring Agent"; script="agents/scoring_agent.py"; port=6003 }
    @{ name="Synth Agent";  script="agents/synth_agent.py";  port=6004 }
)

foreach ($agent in $agents) {
    Write-Host "Starting $($agent.name)..."
    Start-Process -WindowStyle Hidden `
        -FilePath "python" `
        -ArgumentList $agent.script
}

Write-Host ""
Write-Host "================================"
Write-Host "  Checking agent status"
Write-Host "================================"

Start-Sleep -Seconds 2

foreach ($agent in $agents) {
    $port = $agent.port
    $name = $agent.name

    $conn = Test-NetConnection -ComputerName "127.0.0.1" -Port $port -WarningAction SilentlyContinue

    if ($conn.TcpTestSucceeded) {
        Write-Host "[$name] on port $port --> OK"
    } else {
        Write-Host "[$name] on port $port --> FAIL"
    }
}

Write-Host "================================"
Write-Host "Completed."
Write-Host "================================"
