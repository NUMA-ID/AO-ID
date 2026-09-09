#!/bin/bash
# Tunnel SSH inversé persistant vers le poste Windows (NUMA-7QY1DK3)
# Expose AO-ID (8080) et draw.io (8081) en local sur ce PC.
# Se relance automatiquement si la connexion tombe.
#
# Usage : ./tunnel-watchdog.sh (à lancer en arrière-plan, tourne indéfiniment)
# Log   : /home/numa/projets/appel-offre/tunnel-watchdog.log

LOG="/home/numa/projets/appel-offre/tunnel-watchdog.log"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG"
}

log "=== Watchdog démarré (PID $$) ==="

while true; do
  log "Tentative de connexion du tunnel..."
  ssh -p 2222 \
      -N \
      -o ServerAliveInterval=15 \
      -o ServerAliveCountMax=6 \
      -o ExitOnForwardFailure=yes \
      -o TCPKeepAlive=yes \
      -o ConnectTimeout=10 \
      -o StrictHostKeyChecking=accept-new \
      -R 8080:localhost:8080 \
      -R 8081:localhost:8081 \
      administrateur@localhost >> "$LOG" 2>&1

  EXIT_CODE=$?
  log "Tunnel tombé (code $EXIT_CODE). Nouvelle tentative dans 5s..."
  sleep 5
done
