# tunnel-ao-id.ps1
# Lance un tunnel SSH depuis Windows vers djinn-bot
# Redirection des ports 8080 (AO-ID) et 8081 (draw.io)
# Usage: PowerShell -ExecutionPolicy Bypass -File tunnel-ao-id.ps1

$LOG = "$env:USERPROFILE\Downloads\tunnel-ao-id.log"

function Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp $Message" | Out-File -FilePath $LOG -Append
    Write-Host "$timestamp $Message"
}

Log "=== Tunnel AO-ID démarré ==="
Log "Ports redirigés: 8080 (AO-ID), 8081 (draw.io)"
Log "Logs: $LOG"

$retryCount = 0
$maxRetries = 999

while ($retryCount -lt $maxRetries) {
    Log "Tentative de connexion #$($retryCount + 1)..."
    
    # Remplacez "djinn-bot" par l'IP ou le FQDN de votre machine Linux si nécessaire
    # Remplacez "numa" par votre login SSH
    ssh -N `
        -o ServerAliveInterval=15 `
        -o ServerAliveCountMax=6 `
        -o ExitOnForwardFailure=yes `
        -o TCPKeepAlive=yes `
        -o ConnectTimeout=10 `
        -o StrictHostKeyChecking=accept-new `
        -L 8080:localhost:8080 `
        -L 8081:localhost:8081 `
        numa@djinn-bot
    
    $exitCode = $LASTEXITCODE
    Log "Tunnel tombé (code $exitCode). Relance dans 5 secondes..."
    
    $retryCount++
    Start-Sleep -Seconds 5
}

Log "Nombre maximum de tentatives atteint."
