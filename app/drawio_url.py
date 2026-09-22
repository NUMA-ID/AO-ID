# /home/numa/projets/appel-offre/app/drawio_url.py
"""Résolution de l'URL publique de l'éditeur draw.io.

PREPROD (Docker Compose) expose draw.io sur le port 8081 du même hôte.
PROD (Kubernetes) n'expose pas ce port au navigateur : l'éditeur est servi
sous le préfixe /drawio du même origin que AO-ID (HTTPS :443).
"""
from __future__ import annotations


def resolve_drawio_base(
    *,
    override: str = "",
    scheme: str = "https",
    hostname: str = "",
    port: str = "",
) -> str:
    """Retourne l'URL publique de draw.io, sans slash final.

    Args:
        override: valeur explicite (variable d'env DRAWIO_BASE). Prioritaire.
        scheme: http ou https (celui de la page).
        hostname: hôte de la page.
        port: port de la page (chaîne vide si 80/443 implicites).

    Returns:
        URL sans slash final, ex. ``http://localhost:8081`` ou
        ``https://ao-id.one-id.fr/drawio``.
    """
    explicit = (override or "").strip().rstrip("/")
    if explicit:
        return explicit
    port = str(port or "")
    hostname = hostname or ""
    scheme = (scheme or "https").rstrip(":")
    local_ports = {"8080", "8000", "8081"}
    local_hosts = {"localhost", "127.0.0.1"}
    if port in local_ports or hostname in local_hosts:
        return "%s://%s:8081" % (scheme, hostname)
    origin = "%s://%s" % (scheme, hostname)
    if port and port not in {"80", "443"}:
        origin = "%s:%s" % (origin, port)
    return origin + "/drawio"
