#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Appel d'offre ONE ID — backend FastAPI.
Tout-en-un : analyse CCTP via le LLM GB10 (vLLM ONE ID), import Excel Dell, génération du Word ONE ID.
"""
import os, json, tempfile, subprocess, sys, datetime, re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool
from drawio_url import resolve_drawio_base
import recap_cctp as recap_mod
import recap_admin as admin_mod

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine"
WEB = HERE / "web"
ASSETS = HERE / "assets"

BASE_DOCX = os.environ.get("BASE_DOCX", str(ASSETS / "TEMPLATE_BASE_ONEID.docx"))
DOC_BASE = os.environ.get("DOC_BASE", str(HERE.parent / "Documentation_Constructeur"))
OUT_DIR = Path(os.environ.get("OUT_DIR", str(HERE.parent / "Documents_Generes")))
FICHES_DIR = Path(os.environ.get("FICHES_DIR", str(HERE.parent / "Fiches_Specs")))

# Préambule système commun, appliqué à TOUS les appels IA (cadre ONE ID + règles de véracité).
ONEID_PREAMBLE = (
    "Tu agis comme ingénieur avant-vente et directeur technique de ONE ID, intégrateur certifié "
    "Dell Technologies, Fortinet (FortiGate), WithSecure et Sekoia.io (SIEM/SOC). "
    "RÈGLES IMPÉRATIVES, prioritaires sur toute autre instruction : "
    "1) TOUJOURS dire la vérité. "
    "2) NE JAMAIS inventer, extrapoler ni deviner ; si une information n'est pas vérifiable ou absente "
    "des éléments fournis, l'indiquer (« à préciser ») au lieu de l'inventer. "
    "3) N'ajouter aucun fait, chiffre, capacité, quantité, modèle, référence (SKU), prix ni source non "
    "justifié par les données fournies. "
    "4) Rester neutre, objectif et factuel ; prioriser l'exactitude sur le style. "
    "5) Conserver tels quels les marqueurs entre accolades ({client}, {projet}, {rto}, {rpo}, …). "
    "6) Répondre en français. "
    "Applique ces règles en plus de la consigne spécifique ci-dessous."
)


def sysp(specific: str) -> str:
    """Compose le prompt système : préambule ONE ID commun + consigne spécifique."""
    return ONEID_PREAMBLE + "\n\n" + specific


GB10_API_KEY = os.environ.get("GB10_API_KEY", "")
GB10_BASE = os.environ.get("GB10_BASE", "https://llm.one-id.fr/v1")
# Identifiant tel qu'exposé par /v1/models du serveur GB10 (vérifié le 2026-10-06).
# L'ancien défaut "unsloth/Qwen3.8-Flash-Next-GGUF" n'existe plus côté serveur : il ne
# renvoie pas d'erreur mais laisse la requête suspendue jusqu'au timeout.
GB10_MODEL = os.environ.get("GB10_MODEL", "unsloth-oneid/Qwen3.8-Flash-Next-GGUF")
# Moteur IA unique : GB10 (serveur vLLM ONE ID, API OpenAI-compatible).
# Les moteurs Claude / Mammouth / Mistral ont été retirés le 2026-09-09 (décision utilisateur).
DEFAULT_PROVIDER = os.environ.get("DEFAULT_PROVIDER", "gb10").lower()
# URL publique de draw.io (vide = déduite de l'hôte de la requête : :8081 en local, /drawio en prod).
DRAWIO_BASE_ENV = os.environ.get("DRAWIO_BASE", "")

# Réglages LLM persistés (fichier JSON dans OUT_DIR → survit au redémarrage du conteneur,
# monté en volume via docker-compose / PVC Kubernetes). Prend le pas sur les variables d'env.
SETTINGS_FILE = Path(os.environ.get("LLM_SETTINGS_FILE", str(Path(os.environ.get("OUT_DIR",
                     str(HERE.parent / "Documents_Generes"))) / "llm_settings.json")))


def _normalize_base(u: str) -> str:
    """Normalise une base URL LLM : strip, retire slash final. Vide → ''."""
    return (u or "").strip().rstrip("/")


def load_llm_settings() -> dict:
    """Lit le fichier de réglages LLM. Renvoie {} si absent ou illisible.

    Effets de bord : lecture disque (SETTINGS_FILE).
    """
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_llm_settings(data: dict) -> None:
    """Écrit atomiquement le fichier de réglages LLM (0600).

    Effets de bord : écriture disque (SETTINGS_FILE + fichier .tmp temporaire).
    """
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    tmp.replace(SETTINGS_FILE)


def active_llm() -> dict:
    """Retourne la configuration LLM effective : fichier > variables d'environnement.

    Returns:
        dict avec base_url, model, api_key, source ('file' ou 'env'),
        updated_at (float epoch, optionnel), updated_by (str, optionnel).
    """
    s = load_llm_settings()
    if s.get("base_url") and s.get("model") and s.get("api_key"):
        return {"base_url": _normalize_base(s["base_url"]), "model": s["model"],
                "api_key": s["api_key"], "source": "file",
                "updated_at": s.get("updated_at"), "updated_by": s.get("updated_by")}
    return {"base_url": _normalize_base(GB10_BASE), "model": GB10_MODEL,
            "api_key": GB10_API_KEY, "source": "env"}


def _probe_llm(base_url: str, api_key: str, timeout: int = 10) -> dict:
    """Sonde GET {base}/models avec la clé fournie.

    Returns:
        dict {status: 'ok'|'unauthorized'|'unreachable', models: [str], http: int|None}.
    """
    import urllib.request, urllib.error
    url = _normalize_base(base_url) + "/models"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + (api_key or ""),
                                                "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        ids = []
        for m in (d.get("data") or []):
            if isinstance(m, dict) and m.get("id"):
                ids.append(str(m["id"]))
        # Déduplique en préservant l'ordre.
        seen = set(); uniq = []
        for i in ids:
            if i not in seen:
                seen.add(i); uniq.append(i)
        return {"status": "ok", "models": uniq, "http": 200}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"status": "unauthorized", "models": [], "http": e.code}
        return {"status": "unreachable", "models": [], "http": e.code}
    except Exception:
        return {"status": "unreachable", "models": [], "http": None}


def llm_complete(system, user, max_tokens=4000, provider="", model=""):
    """Appelle le moteur IA GB10 (serveur vLLM ONE ID, API OpenAI-compatible).

    Args:
        system: prompt système (cadre ONE ID + consigne spécifique).
        user: contenu utilisateur.
        max_tokens: plafond de tokens générés.
        provider: conservé pour compatibilité d'appel ; seul 'gb10' est desservi.
        model: identifiant de modèle vLLM ; défaut GB10_MODEL.

    Returns:
        Le contenu texte final de la réponse (le raisonnement intermédiaire
        éventuel — champ reasoning_content — est ignoré).

    Raises:
        HTTPException 400 si aucune clé configurée ; 502 sur erreur de l'API GB10.
    """
    cfg = active_llm()
    if not cfg["api_key"]:
        raise HTTPException(400, "Clé API LLM non configurée (voir ⚙ Paramètres LLM ou fichier .env).")
    import urllib.request, urllib.error
    payload = {
        "model": model or cfg["model"], "max_tokens": max_tokens,
        # Streaming SSE : indispensable pour tenir les longues générations sur GB10.
        # Bifrost coupe une requête non-stream à 300 s d'attente ; en stream la connexion
        # reçoit des chunks régulièrement et n'est jamais idle.
        "stream": True,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    # reasoning_effort n'est envoyé qu'aux modèles "thinking" / "reasoning" (Qwen3-Thinking,
    # gpt-oss, o1…). Sur un modèle instruct classique (qwen3-coder-30b), Bifrost peut le refuser
    # ou l'ignorer silencieusement — préfère ne pas l'envoyer pour éviter tout effet de bord.
    mdl = (model or cfg["model"]).lower()
    if any(k in mdl for k in ("thinking", "reasoning", "flash-next", "gpt-oss", "qwen3.5", "qwen3.8")):
        payload["reasoning_effort"] = os.environ.get("LLM_REASONING_EFFORT", "medium")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        cfg["base_url"] + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + cfg["api_key"],
                 "Content-Type": "application/json",
                 "Accept": "text/event-stream"})
    # Timeout 900s : buffer de sécurité, mais le stream envoie des chunks bien avant.
    try:
        parts = []
        with urllib.request.urlopen(req, timeout=900) as resp:
            # Lecture SSE : chaque event = "data: {json}\n\n". "data: [DONE]" clôt le flux.
            buf = b""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    event, buf = buf.split(b"\n\n", 1)
                    for line in event.split(b"\n"):
                        if not line.startswith(b"data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == b"[DONE]":
                            continue
                        try:
                            j = json.loads(data.decode("utf-8"))
                        except Exception:
                            continue
                        ch = (j.get("choices") or [{}])[0]
                        delta = ch.get("delta") or {}
                        # Certains modèles envoient reasoning en delta séparé — on l'ignore.
                        piece = delta.get("content") or ""
                        if piece:
                            parts.append(piece)
        return "".join(parts)
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            detail = ""
        raise HTTPException(502, "Erreur API GB10 (HTTP %s) : %s" % (e.code, detail or e.reason))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, "Erreur API GB10 : " + str(e))

OUT_DIR.mkdir(parents=True, exist_ok=True)
FICHES_DIR.mkdir(parents=True, exist_ok=True)

APP_VERSION = "2.7"


def _archive_frontend():
    """Conserve une copie horodatée de l'interface par version (snapshot fidèle, fait dans le conteneur)."""
    try:
        import shutil
        src = WEB / "index.html"
        vdir = WEB / "versions"; vdir.mkdir(exist_ok=True)
        dst = vdir / ("index_v%s.html" % APP_VERSION)
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
    except Exception:
        pass


_archive_frontend()

app = FastAPI(title="Appel d'offre ONE ID")


def slug(s, n=40):
    return (re.sub(r"[^a-z0-9]+", "_", (s or "client").lower()).strip("_") or "client")[:n]


# ---------------------------------------------------------------- Frontend
def _build_stamp():
    """Date du dernier build = mtime le plus récent des fichiers de l'app (change à chaque déploiement)."""
    files = [WEB / "index.html", HERE / "main.py", ENGINE / "generer_doc.py"]
    mts = [p.stat().st_mtime for p in files if p.exists()]
    if not mts:
        return ""
    return datetime.datetime.fromtimestamp(max(mts)).strftime("%Y-%m-%d %H:%M")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    f = WEB / "index.html"
    if not f.exists():
        return HTMLResponse("<h1>Frontend manquant</h1>", status_code=500)
    host = request.headers.get("host") or request.url.hostname or ""
    hostname = host.split(":")[0]
    port = host.split(":")[1] if ":" in host else (str(request.url.port or "") if request.url.port else "")
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    drawio_base = resolve_drawio_base(
        override=DRAWIO_BASE_ENV, scheme=scheme, hostname=hostname, port=port,
    )
    html = (f.read_text(encoding="utf-8")
            .replace("__BUILD__", _build_stamp())
            .replace("__DRAWIO_BASE__", drawio_base))
    return HTMLResponse(html)


@app.get("/api/health")
def health():
    cfg = active_llm()
    return {"ok": True, "model": cfg["model"], "api_key_set": bool(cfg["api_key"]),
            "base_url": cfg["base_url"], "source": cfg["source"],
            "doc_base": DOC_BASE, "out_dir": str(OUT_DIR)}


# ---------------------------------------------------------------- Paramètres LLM (UI)
def _mask_key(k: str) -> str:
    if not k:
        return ""
    if len(k) <= 8:
        return "*" * len(k)
    return k[:4] + "…" + k[-4:]


@app.get("/api/settings/llm")
def get_llm_settings():
    """Retourne la config LLM active (SANS la clé en clair, uniquement masquée).

    Effets de bord : lecture SETTINGS_FILE.
    """
    cfg = active_llm()
    return {"base_url": cfg["base_url"], "model": cfg["model"],
            "api_key_masked": _mask_key(cfg["api_key"]),
            "source": cfg["source"],
            "updated_at": cfg.get("updated_at"),
            "updated_by": cfg.get("updated_by")}


@app.put("/api/settings/llm")
def put_llm_settings(payload: dict):
    """Enregistre base_url + model + api_key. Si api_key vide, conserve la clé actuelle.

    Effets de bord : lecture/écriture SETTINGS_FILE, appel réseau vers base_url.
    Raises: 400 (base_url ou model manquant, ou clé refusée), 502 (LLM injoignable).
    """
    base_url = _normalize_base((payload or {}).get("base_url", ""))
    model = ((payload or {}).get("model") or "").strip()
    api_key = ((payload or {}).get("api_key") or "").strip()
    if not base_url or not model:
        raise HTTPException(400, "base_url et model sont requis.")
    # Clé vide → on garde celle déjà enregistrée (fichier > env). Permet de changer juste le modèle.
    if not api_key:
        current = active_llm()
        api_key = current["api_key"]
        if not api_key:
            raise HTTPException(400, "Aucune clé actuellement enregistrée : saisissez-en une.")
    probe = _probe_llm(base_url, api_key)
    if probe["status"] == "unauthorized":
        raise HTTPException(400, "Clé API refusée par le serveur LLM.")
    # On tolère unreachable (on enregistre quand même mais on signale).
    data = {"base_url": base_url, "model": model, "api_key": api_key,
            "updated_at": datetime.datetime.now().timestamp(),
            "updated_by": (payload or {}).get("updated_by") or ""}
    save_llm_settings(data)
    if probe["status"] == "ok":
        return {"ok": True, "nb_modeles_listes": len(probe["models"]), "probe": "ok"}
    # unreachable
    return JSONResponse(status_code=502,
                        content={"ok": False, "detail": {"probe": "failed_saved_anyway"}})


@app.post("/api/settings/llm/probe")
def probe_llm_settings(payload: dict):
    """Sonde une base_url + api_key sans rien persister.

    Effets de bord : appel réseau vers base_url. Raises: 422 si champs manquants.
    """
    base_url = _normalize_base((payload or {}).get("base_url", ""))
    api_key = ((payload or {}).get("api_key") or "").strip()
    if not base_url or not api_key:
        raise HTTPException(422, "base_url et api_key sont requis.")
    p = _probe_llm(base_url, api_key)
    return {"status": p["status"], "nb_modeles": len(p["models"]), "models": p["models"]}


@app.get("/api/settings/llm/models")
def list_llm_models(probe_url: str = ""):
    """Liste les modèles exposés par le LLM avec la clé enregistrée.

    Effets de bord : lecture SETTINGS_FILE, appel réseau. Raises: 400 (pas de clé), 502.
    """
    cfg = active_llm()
    if not cfg["api_key"]:
        raise HTTPException(400, "Aucune clé enregistrée.")
    base = _normalize_base(probe_url) or cfg["base_url"]
    p = _probe_llm(base, cfg["api_key"])
    if p["status"] == "unauthorized":
        raise HTTPException(400, "Clé enregistrée refusée par le LLM.")
    if p["status"] != "ok":
        raise HTTPException(502, "Serveur LLM injoignable.")
    return {"models": p["models"]}


# ---------------------------------------------------------------- Extraction texte
def _docx_to_text(doc) -> str:
    """Paragraphes puis tableaux d'un document python-docx (cellules séparées par « | »)."""
    out = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for t in doc.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                out.append(" | ".join(cells))
    return "\n".join(out)


def extract_docx_text(path) -> str:
    """Extrait le texte (paragraphes + tableaux) d'un .docx généré, pour la comparaison CCTP."""
    import docx
    return _docx_to_text(docx.Document(str(path)))


def extract_xlsx_text(data: bytes) -> str:
    """Extrait le texte d'un classeur .xlsx/.xlsm : une section par feuille, une ligne par rangée.

    Valeurs calculées (``data_only=True`` : résultat des formules tel qu'enregistré par Excel),
    cellules vides ignorées, cellules d'une rangée séparées par « | ».
    Effets de bord : aucun (lecture en mémoire).
    """
    import io
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out: list[str] = []
    try:
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                out.append("### Feuille : %s\n%s" % (ws.title, "\n".join(rows)))
    finally:
        wb.close()
    return "\n\n".join(out)


def extract_text(filename: str, data: bytes) -> str:
    """Extrait le texte d'un document déposé (.txt, .docx, .pdf, .xlsx/.xlsm ; sinon décodage UTF-8).

    Le .docx inclut désormais ses tableaux (AE, annexes financières…).
    Raises:
        ValueError: format .xls (Excel 97-2003) non pris en charge.
    """
    name = (filename or "").lower()
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="replace")
    if name.endswith(".docx"):
        import docx, io
        return _docx_to_text(docx.Document(io.BytesIO(data)))
    if name.endswith((".xlsx", ".xlsm")):
        return extract_xlsx_text(data)
    if name.endswith(".xls"):
        raise ValueError("format .xls non pris en charge : enregistrez le classeur en .xlsx")
    if name.endswith(".pdf"):
        import pdfplumber, io
        out = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for pg in pdf.pages:
                out.append(pg.extract_text() or "")
        return "\n".join(out)
    # fallback : tenter en texte
    return data.decode("utf-8", errors="replace")


def parse_json_loose(s: str):
    try:
        return json.loads(s)
    except Exception:
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(s[a:b + 1])
            except Exception:
                return None
    return None


def _unesc(x):
    return (x or "").replace("\\n", "\n").replace("\\r", "").replace("\\t", " ").replace('\\"', '"').replace("\\/", "/").strip()


def parse_cctp(raw):
    """Extraction robuste de l'analyse CCTP : JSON propre, sinon récupération tolérante (JSON mal formé)."""
    s = (raw or "").strip()
    s = re.sub(r"```(?:json)?", "", s).replace("```", "").strip()   # retire les fences, même non fermés
    data = parse_json_loose(s)
    if isinstance(data, dict) and (data.get("contexte") or data.get("points")):
        return {"contexte": (data.get("contexte") or "").strip(),
                "points": data.get("points") or [],
                "clarifications": data.get("clarifications") or [],
                "verification": data.get("verification") or [], "ok": True}
    # Récupération tolérante (sauts de ligne non échappés, guillemets, sortie tronquée…)
    ctx = ""
    m = re.search(r'"contexte"\s*:\s*"(.*?)"\s*,\s*"(?:points|clarifications|verification)"', s, re.S)
    if not m:
        m = re.search(r'"contexte"\s*:\s*"(.*)$', s, re.S)   # contexte tronqué en fin de sortie
    if m:
        ctx = _unesc(m.group(1)).rstrip('"}').strip()

    def arr(name):
        am = re.search(r'"' + name + r'"\s*:\s*\[(.*?)\]', s, re.S)
        if not am:
            return []
        return [_unesc(x) for x in re.findall(r'"((?:[^"\\]|\\.)*)"', am.group(1)) if x.strip()]

    return {"contexte": ctx, "points": arr("points"), "clarifications": arr("clarifications"),
            "verification": [], "ok": bool(ctx or arr("points"))}


CCTP_PROMPT = (
    "Tu es ingénieur avant-vente en infrastructure (Dell, stockage, sauvegarde, virtualisation). "
    "À partir du TEXTE DE CCTP fourni, et de la SOLUTION CONFIGURÉE si elle est présente, renvoie "
    "UNIQUEMENT un objet JSON valide, sans texte autour, de la forme : "
    '{"contexte":"...","points":["..."],"clarifications":["..."],'
    '"verification":[{"theme":"...","exigence":"...","statut":"couvert|ecart|a_preciser","suggestion":"..."}]}. '
    "Règles strictes : rester factuel et fidèle au CCTP, NE RIEN INVENTER ; si une information manque, "
    "ne pas l'ajouter. \"contexte\" = résumé professionnel (2 à 4 paragraphes) du contexte, des objectifs et "
    "de l'existant, destiné à un document client, en français. \"points\" = checklist interne des points "
    "d'attention techniques repérés (RPO/RTO, réplication, immuabilité/airgap, sauvegarde, volumétrie, "
    "licences, migration AD/messagerie, réseau, sécurité/EDR, conformité RGPD/RGS/ANSSI, garanties, "
    "reconditionné, etc.). \"clarifications\" = incohérences ou zones d'ombre à faire préciser. "
    "\"verification\" = comparaison entre les EXIGENCES du CCTP — techniques ET administratives "
    "(volumétrie, RPO/RTO, sauvegarde/PRA, sécurité/EDR, réseau, licences, garanties, reconditionné, "
    "délais, critères d'attribution, pièces à fournir, RGPD/RGS/ANSSI, etc.) — et la SOLUTION CONFIGURÉE "
    "fournie. statut='couvert' si la solution répond à l'exigence, 'ecart' si une exigence n'est pas "
    "couverte, 'a_preciser' s'il manque l'information pour trancher. \"suggestion\" = information à ajouter "
    "ou point à vérifier, formulé prudemment, SANS inventer de donnée technique précise non justifiée. "
    "Si aucune solution n'est fournie, marque les exigences en 'a_preciser'. En français."
)


def summarize_solution(sol):
    """Résumé textuel court de la solution configurée pour la comparaison CCTP."""
    if not sol:
        return ""
    try:
        d = json.loads(sol) if isinstance(sol, str) else sol
    except Exception:
        return ""
    if not isinstance(d, dict):
        return ""
    lines = []
    aff = d.get("affaire", {}) or {}
    if aff.get("solution_proposee"):
        lines.append("Description de la solution : " + str(aff["solution_proposee"]))
    cats = [("serveurs", "Serveurs"), ("stockages", "Stockage"), ("switches", "Switches"),
            ("sauvegardes", "Sauvegarde"), ("logiciels_services", "Logiciels/Services")]
    for key, lab in cats:
        items = d.get(key) or []
        if not items:
            continue
        parts = []
        for it in items:
            if not isinstance(it, dict):
                continue
            nm = it.get("modele") or it.get("role") or it.get("designation") or it.get("nom") or ""
            q = it.get("qte") or it.get("quantite") or ""
            extra = [str(it[f]) for f in ("cpu_fam", "ram_total", "raw", "utile", "type_disque", "os") if it.get(f)]
            label = ((str(q) + "x ") if q else "") + str(nm) + ((" (" + ", ".join(extra) + ")") if extra else "")
            if label.strip():
                parts.append(label)
        if parts:
            lines.append(lab + " : " + " ; ".join(parts))
    # PRA / PCA
    pp = aff.get("pra_pca") or {}
    if pp.get("actif"):
        lines.append("Dispositif %s : RTO %s, RPO %s, cible %s, méthode %s" % (
            (pp.get("mode") or "").upper(), pp.get("rto") or "?", pp.get("rpo") or "?",
            pp.get("cible") or "?", pp.get("methode") or "?"))
    # Sauvegarde (module Fonctionnalité)
    sv = d.get("sauvegarde") or {}
    if sv.get("logiciel") or sv.get("cible"):
        lines.append("Sauvegarde : logiciel %s, cible %s, licence %s%s" % (
            sv.get("logiciel") or "?", sv.get("cible") or "?", sv.get("licence") or "?",
            ", réplication Cloud ONE ID" if sv.get("cloud") else ""))
        for s in (sv.get("sites") or []):
            cells = s.get("cells") or {}
            tb = cells.get("TB") or {}
            if tb:
                lines.append("  Volumétrie %s (TB) : %s" % (s.get("nom") or "site",
                             ", ".join("%s=%s" % (k, v) for k, v in tb.items() if v)))
    # Chapitres rédigés (Kanban)
    chaps = d.get("chapitres") or []
    titres = [c.get("titre") for c in chaps if isinstance(c, dict) and (c.get("titre") or "").strip()]
    if titres:
        lines.append("Chapitres rédigés : " + " ; ".join(titres))
    return "\n".join(lines)


@app.post("/api/analyse-cctp")
async def analyse_cctp(file: UploadFile = File(None), text: str = Form(None), solution: str = Form(None),
                       provider: str = Form(DEFAULT_PROVIDER), model: str = Form("")):
    cctp = ""
    if file is not None:
        cctp = extract_text(file.filename, await file.read())
    elif text:
        cctp = text
    cctp = (cctp or "").strip()
    if not cctp:
        raise HTTPException(400, "CCTP vide : fournissez un fichier (PDF/Word/TXT) ou du texte.")
    sol_summary = summarize_solution(solution)
    # Bifrost gateway coupe à 300 s. Sur qwen3-coder-30b, ~60 K chars d'entrée + 4 K tokens
    # de sortie tiennent dans le budget. Au-delà, l'utilisateur peut coller le CCTP par tranches.
    user = "TEXTE DU CCTP :\n\n" + cctp[:60000]
    if sol_summary:
        user += "\n\nSOLUTION ACTUELLEMENT CONFIGURÉE :\n" + sol_summary[:15000]
    else:
        user += "\n\n(Aucune solution configurée pour le moment : marque les exigences en 'a_preciser'.)"
    raw = await run_in_threadpool(llm_complete, sysp(CCTP_PROMPT), user, 4000, provider, model)
    p = parse_cctp(raw)
    contexte, points = p["contexte"], p["points"]
    clarifications, verification = p["clarifications"], p["verification"]
    if not p["ok"]:
        contexte = contexte or ("L'analyse n'a pas pu être structurée automatiquement. "
                                "Réessayez, ou changez de moteur IA (barre du bas).")
    return {"contexte": contexte, "points": points,
            "clarifications": clarifications, "verification": verification, "cctp_text": cctp,
            "raw": "" if p["ok"] else raw}


# ---------------------------------------------------------------- Récapitulatif CCTP — Focus technique (étape 2)
@app.post("/api/recap-cctp")
async def recap_cctp(payload: dict):
    """Génère les 3 tableaux du récapitulatif CCTP (matrice, plan, ressources) via le LLM.

    Entrée JSON : cctp_text (str, requis), points (list), clarifications (list),
    solution (dict fiche, optionnel), provider/model (str, optionnels).
    Sortie : {matrice, plan, ressources, ok, raw}. raw = texte LLM brut si ok est False.
    Erreurs : 400 si CCTP vide ; 400/502 remontées par llm_complete.
    Effet de bord : un appel réseau au LLM (aucune écriture disque).
    """
    cctp = (payload.get("cctp_text") or "").strip()
    if not cctp:
        raise HTTPException(400, "Analysez ou collez d'abord le CCTP avant de générer le récapitulatif.")
    user = recap_mod.build_user_message(cctp, payload.get("points"), payload.get("clarifications"),
                                        summarize_solution(payload.get("solution")))
    raw = await run_in_threadpool(llm_complete, sysp(recap_mod.RECAP_PROMPT), user, 6000,
                                  payload.get("provider"), payload.get("model"))
    rec = recap_mod.parse_recap(raw)
    return {**rec, "raw": "" if rec["ok"] else (raw or "")[:4000]}


# ---------------------------------------------------------------- Focus administratif et contractuel (étape 3)
ADMIN_DOC_MAX = 150000   # caractères conservés par document administratif (renvoyés au front, stockés en fiche)
ADMIN_DOC_EXT = (".pdf", ".docx", ".txt", ".xlsx", ".xlsm")


@app.post("/api/admin-docs/extract")
async def admin_docs_extract(files: list[UploadFile] = File(...)):
    """Extrait le texte des documents administratifs du DCE (RC, CCAP, AE, BPU/DPGF…).

    Entrée : multipart, un ou plusieurs fichiers PDF / DOCX / TXT / XLSX / XLSM (champ ``files``).
    Sortie : ``{docs: [{name, text, chars, truncated}], budget}``. Le texte est tronqué à
    ``ADMIN_DOC_MAX`` caractères ; ``chars`` est la longueur avant troncature ; ``budget`` =
    caractères analysés au total par /api/recap-admin (``recap_admin.MAX_INPUT``).
    Erreurs : 400 si un format n'est pas pris en charge (.doc, .xls, autre) ou si aucun texte
    n'est extrait.
    Effets de bord : aucun (traitement en mémoire, rien n'est écrit sur disque).
    """
    out = []
    for f in files:
        name = Path(f.filename or "document").name
        if not name.lower().endswith(ADMIN_DOC_EXT):
            raise HTTPException(400, "« %s » : format non pris en charge (acceptés : PDF, DOCX, TXT, XLSX). "
                                     "Enregistrez les .doc en .docx et les .xls en .xlsx." % name)
        try:
            text = (extract_text(name, await f.read()) or "").strip()
        except Exception as e:
            raise HTTPException(400, "« %s » : lecture impossible (%s)." % (name, e))
        out.append({"name": name, "text": text[:ADMIN_DOC_MAX], "chars": len(text),
                    "truncated": len(text) > ADMIN_DOC_MAX})
    if not any(d["text"] for d in out):
        raise HTTPException(400, "Aucun texte lisible dans les documents fournis (PDF scanné ?).")
    return {"docs": out, "budget": admin_mod.MAX_INPUT}


@app.post("/api/recap-admin")
async def recap_admin(payload: dict):
    """Génère le focus administratif et contractuel (checklist, points contractuels, questions PLACE).

    Entrée JSON : docs ([{name, text}], documents administratifs déjà extraits), cctp_text (str,
    optionnel, ajouté en contexte), provider/model (optionnels). Au moins des docs ou un CCTP.
    Sortie : ``{reference_marche, date_limite_questions, date_limite_offres, checklist,
    contractuel, questions, ok, raw, prompt}``.
    Erreurs : 400 si ni document ni CCTP ; 400/502 remontées par llm_complete.
    Effet de bord : un appel réseau au LLM (aucune écriture disque).
    """
    docs = [(str(d.get("name") or "document"), str(d.get("text") or ""))
            for d in (payload.get("docs") or []) if isinstance(d, dict)]
    cctp = (payload.get("cctp_text") or "").strip()
    if not any(t.strip() for _, t in docs) and not cctp:
        raise HTTPException(400, "Chargez d'abord les documents administratifs (RC, CCAP, AE…) ou analysez le CCTP.")
    user = admin_mod.build_user_message(docs, cctp)
    raw = await run_in_threadpool(llm_complete, sysp(admin_mod.RECAP_ADMIN_PROMPT), user, 6000,
                                  payload.get("provider") or "", payload.get("model") or "")
    res = admin_mod.parse_admin(raw)
    return {**res, "raw": "" if res["ok"] else (raw or "")[:4000], "prompt": admin_mod.RECAP_ADMIN_PROMPT}


# ---------------------------------------------------------------- Import Excel Dell
@app.post("/api/import-excel")
async def import_excel(file: UploadFile = File(...)):
    raw = await file.read()
    with tempfile.TemporaryDirectory() as td:
        xlsx = Path(td) / "in.xlsx"
        out = Path(td) / "fiche.json"
        xlsx.write_bytes(raw)
        r = subprocess.run([sys.executable, str(ENGINE / "parser_dell_excel.py"), str(xlsx), str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            # Log le traceback complet côté serveur (non tronqué) pour le diagnostic ;
            # la réponse HTTP reste tronquée à 500 caractères pour ne pas surcharger l'UI.
            print("ERREUR /api/import-excel — sortie complète du parseur :\n" + (r.stderr or r.stdout), flush=True)
            raise HTTPException(500, "Échec du parseur Excel : " + (r.stderr or r.stdout)[:500])
        return JSONResponse(json.loads(out.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- Proposition de chapitres (Kanban)
CHAP_PROMPT = (
    "Tu es ingénieur avant-vente en infrastructure. On te fournit une liste de POINTS D'ATTENTION "
    "techniques issus d'un CCTP. Regroupe-les en CHAPITRES thématiques à rédiger dans un mémoire "
    "technique d'appel d'offre (par exemple : Licences, Migration messagerie, Stockage, Sauvegarde et "
    "PRA/PCA, Sécurité, Réseau, Virtualisation, Garanties et support, Conformité). "
    "Renvoie UNIQUEMENT un objet JSON valide : {\"chapitres\":[{\"titre\":\"...\",\"cartes\":[\"...\"]}]}. "
    "RÈGLES STRICTES : place dans \"cartes\" le TEXTE EXACT des points fournis (verbatim, sans reformuler), "
    "n'invente AUCUN point, n'ajoute rien. Chaque point apparaît dans au plus un chapitre. Classe les "
    "chapitres dans un ordre logique de rédaction. Donne des titres de chapitres courts et explicites. En français."
)


@app.post("/api/proposer-chapitres")
async def proposer_chapitres(payload: dict):
    pts = [str(p).strip() for p in (payload.get("points") or []) if str(p).strip()]
    if not pts:
        raise HTTPException(400, "Aucun point d'attention à regrouper (analysez d'abord le CCTP).")
    user = "POINTS D'ATTENTION :\n" + "\n".join("- " + p for p in pts)
    raw = await run_in_threadpool(llm_complete, sysp(CHAP_PROMPT), user, 4000, payload.get("provider"), payload.get("model"))
    cleaned = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if m:
        cleaned = m.group(1).strip()
    data = parse_json_loose(cleaned) or {}
    return {"chapitres": data.get("chapitres") or []}


# ---------------------------------------------------------------- Vérification de conformité (bouton dédié)
VERIF_PROMPT = (
    "Tu es ingénieur avant-vente en infrastructure (Dell, stockage, sauvegarde, virtualisation, sécurité). "
    "Compare les EXIGENCES du CCTP — techniques ET administratives (volumétrie, RPO/RTO, sauvegarde/PRA, "
    "immuabilité/airgap, sécurité/EDR, réseau, virtualisation, licences, garanties, reconditionné, délais, "
    "critères d'attribution, pièces à fournir, RGPD/RGS/ANSSI, etc.) — à la SOLUTION CONFIGURÉE fournie. "
    "Renvoie UNIQUEMENT un objet JSON valide, sans texte autour, de la forme : "
    '{"verification":[{"theme":"...","exigence":"...","statut":"couvert|ecart|a_preciser","suggestion":"..."}]}. '
    "statut='couvert' si la solution répond à l'exigence, 'ecart' si une exigence n'est pas couverte, "
    "'a_preciser' s'il manque l'information pour trancher. \"suggestion\" = information à ajouter ou point à "
    "vérifier, formulé prudemment. RÈGLE ABSOLUE : NE RIEN INVENTER, aucune donnée technique précise non "
    "justifiée. Si aucune solution n'est fournie, marque les exigences en 'a_preciser'. En français."
)


@app.post("/api/verifier")
async def verifier(payload: dict):
    cctp = (payload.get("cctp_text") or "").strip()
    if not cctp:
        raise HTTPException(400, "Analysez ou collez d'abord le CCTP avant de vérifier la conformité.")
    # Priorité : lire le VRAI document Word généré si fourni ; sinon repli sur le résumé configuré.
    doc_text, source = "", ""
    gen = payload.get("generated_file")
    if gen:
        p = OUT_DIR / Path(str(gen)).name
        if p.exists() and p.suffix.lower() == ".docx":
            try:
                doc_text = extract_docx_text(p); source = "document Word généré"
            except Exception:
                doc_text = ""
    if not doc_text:
        doc_text = summarize_solution(payload.get("solution")); source = "solution configurée"
    user = "TEXTE DU CCTP :\n\n" + cctp[:120000]
    user += ("\n\nCONTENU DE L'AO (%s) :\n%s" % (source, doc_text[:80000])) if doc_text else \
            "\n\n(Aucun contenu d'AO fourni : marque les exigences en 'a_preciser'.)"
    raw = await run_in_threadpool(llm_complete, sysp(VERIF_PROMPT), user, 6000, payload.get("provider"), payload.get("model"))
    cleaned = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if m:
        cleaned = m.group(1).strip()
    data = parse_json_loose(cleaned) or {}
    return {"verification": data.get("verification") or []}


# ---------------------------------------------------------------- Mode Design (moteur GB10)
DESIGN_PROMPT = (
    "Tu es rédacteur technique avant-vente ONE ID. On te fournit un JSON contenant des champs "
    "narratifs d'un document d'appel d'offre. Améliore UNIQUEMENT le style, la clarté, la structure "
    "et le professionnalisme du texte en français. "
    "RÈGLES ABSOLUES : ne JAMAIS inventer, ajouter, supprimer ni modifier un fait, un chiffre, une "
    "capacité, une quantité, un nom de produit, une référence (SKU), un prix ou une donnée technique. "
    "Tu peux uniquement reformuler et réorganiser le texte fourni. Conserve EXACTEMENT les marqueurs "
    "entre accolades comme {client} ou {projet}. Tu peux structurer en paragraphes et en listes à "
    "puces (chaque puce préfixée par '- '). "
    "Renvoie UNIQUEMENT un objet JSON valide, sans texte autour, de la forme : "
    '{"intro":"...","contexte":"...","solution_proposee":"...",'
    '"theme":{"primary":"#RRGGBB","accent":"#RRGGBB"}}. '
    "Si un champ d'entrée est vide, renvoie-le vide. Le thème doit rester sobre et corporate "
    "(tons bleus/gris foncés), 'primary' servant à colorer les titres et en-têtes de tableaux."
)


def design_enhance(aff: dict, provider="", model="") -> dict:
    payload = {
        "intro": aff.get("intro_override") or "",
        "contexte": aff.get("contexte") or aff.get("notes") or "",
        "solution_proposee": aff.get("solution_proposee") or "",
    }
    raw = llm_complete(sysp(DESIGN_PROMPT),
                       "JSON à améliorer :\n" + json.dumps(payload, ensure_ascii=False),
                       4000, provider, model)
    cleaned = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if m:
        cleaned = m.group(1).strip()
    return parse_json_loose(cleaned) or {}


# ---------------------------------------------------------------- Reformulation "Solution proposée"
SOLUTION_PROMPT = (
    "Tu es ingénieur avant-vente senior chez ONE ID, intégrateur certifié Dell Technologies, "
    "Fortinet, WithSecure et Sekoia.io. On te fournit une description BRUTE de la solution "
    "proposée à un client. Réécris-la en français comme si TU l'avais rédigée toi-même pour ce "
    "client : un texte clair, fluide, en phrases complètes, à la première personne du pluriel "
    "(\"nous\", \"ONE ID\"). "
    "Ton humain et naturel d'expert qui maîtrise son sujet — surtout PAS un style d'IA : évite les "
    "formules génériques, les superlatifs creux, les tournures du type \"En conclusion\"/\"il convient "
    "de noter\", et les listes artificielles. On ne doit pas pouvoir deviner que c'est généré. "
    "Mets en avant des arguments commerciaux concrets qui donnent envie de choisir la solution "
    "(bénéfices métier, fiabilité, performances, sécurité, évolutivité, accompagnement ONE ID), mais "
    "UNIQUEMENT à partir des éléments fournis. "
    "RÈGLE ABSOLUE : n'invente, n'ajoute ni ne modifie AUCUN fait, chiffre, capacité, quantité, "
    "modèle ni référence. Tu reformules et valorises ce qui est donné, sans rien ajouter d'inexact. "
    "Tu peux organiser en quelques paragraphes ; pour une puce, préfixe la ligne par '- '. Conserve "
    "tels quels les marqueurs {client} et {projet} s'ils sont présents (n'en ajoute pas sinon). "
    "Renvoie UNIQUEMENT le texte réécrit, sans guillemets ni commentaire autour."
)


@app.post("/api/ameliorer-solution")
async def ameliorer_solution(payload: dict):
    texte = (payload.get("text") or "").strip()
    if not texte:
        raise HTTPException(400, "Aucun texte à reformuler.")
    ctx = []
    if payload.get("client"):
        ctx.append("Client : " + str(payload["client"]))
    if payload.get("projet"):
        ctx.append("Projet : " + str(payload["projet"]))
    user = (("\n".join(ctx) + "\n\n") if ctx else "") + "Description brute à réécrire :\n" + texte
    out = (await run_in_threadpool(llm_complete, sysp(SOLUTION_PROMPT), user, 3000, payload.get("provider"), payload.get("model"))).strip()
    return {"text": out}


# ---------------------------------------------------------------- Chiffrage (Excel)
def _duree_jours(s):
    s = str(s or "").lower().replace(",", ".")
    import re as _re
    n = 0.0
    sm = _re.search(r"([\d.]+)\s*s", s); jm = _re.search(r"([\d.]+)\s*j", s)
    if sm: n += float(sm.group(1)) * 5
    if jm: n += float(jm.group(1))
    if not sm and not jm:
        try: n = float(s)
        except Exception: n = 0
    return round(n, 2)


def build_chiffrage_xlsx(spec, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    aff = spec.get("affaire", {}) or {}
    wb = Workbook(); ws = wb.active; ws.title = "Chiffrage"
    NAVY = "0A3D62"; RED = "C00000"
    hdr_fill = PatternFill("solid", fgColor=NAVY)
    sec_fill = PatternFill("solid", fgColor="D6E4EF")
    thin = Side(style="thin", color="D9D9D9"); border = Border(left=thin, right=thin, top=thin, bottom=thin)
    money = "#,##0.00 €"
    ws.column_dimensions["A"].width = 46
    for col in ("B", "C", "D", "E"):
        ws.column_dimensions[col].width = 16
    r = 1
    ws.cell(r, 1, "Chiffrage — %s / %s" % (aff.get("client") or "", aff.get("projet") or "")).font = Font(bold=True, size=14, color=NAVY)
    r += 2

    def section_header(title):
        nonlocal r
        c = ws.cell(r, 1, title); c.font = Font(bold=True, color=NAVY); c.fill = sec_fill
        for col in range(2, 6):
            ws.cell(r, col).fill = sec_fill
        r += 1

    def col_headers(cols):
        nonlocal r
        for i, h in enumerate(cols, 1):
            c = ws.cell(r, i, h); c.font = Font(bold=True, color="FFFFFF"); c.fill = hdr_fill
            c.alignment = Alignment(horizontal="center"); c.border = border
        r += 1

    # --- Matériel ---
    section_header("MATÉRIEL")
    col_headers(["Désignation", "Référence (SKU)", "Qté", "PU HT", "Total HT"])
    first_mat = r
    cats = [("serveurs",), ("stockages",), ("switches",), ("sauvegardes",), ("logiciels_services",)]
    any_mat = False
    for (key,) in cats:
        for it in (spec.get(key) or []):
            if not isinstance(it, dict):
                continue
            desig = it.get("modele") or it.get("role") or it.get("designation") or it.get("nom") or ""
            if not str(desig).strip():
                continue
            any_mat = True
            try: qte = int(str(it.get("qte") or it.get("quantite") or 1))
            except Exception: qte = 1
            pu = it.get("prix") or it.get("pu") or it.get("prix_unitaire") or ""
            ws.cell(r, 1, str(desig)).border = border
            ws.cell(r, 2, str(it.get("sku") or "")).border = border
            ws.cell(r, 3, qte).border = border
            cpu = ws.cell(r, 4); cpu.border = border; cpu.number_format = money
            try: cpu.value = float(str(pu).replace(",", ".").replace("€", "").strip())
            except Exception: pass
            ct = ws.cell(r, 5, "=C%d*D%d" % (r, r)); ct.border = border; ct.number_format = money
            r += 1
    if not any_mat:
        ws.cell(r, 1, "(aucun équipement)").border = border; r += 1
    last_mat = r - 1
    ws.cell(r, 1, "Sous-total matériel HT").font = Font(bold=True)
    st_mat = ws.cell(r, 5, "=SUM(E%d:E%d)" % (first_mat, last_mat)); st_mat.font = Font(bold=True); st_mat.number_format = money
    row_mat = r; r += 2

    # --- Prestations ---
    section_header("PRESTATIONS")
    col_headers(["Désignation", "Durée (j)", "Tarif/j HT", "Total HT"])
    first_pr = r
    prs = [p for p in (spec.get("prestations") or []) if isinstance(p, dict) and (p.get("intitule") or "").strip()]
    for p in prs:
        ws.cell(r, 1, p.get("intitule")).border = border
        ws.cell(r, 2, _duree_jours(p.get("duree"))).border = border
        ct = ws.cell(r, 3); ct.border = border; ct.number_format = money
        tot = ws.cell(r, 4, "=B%d*C%d" % (r, r)); tot.border = border; tot.number_format = money
        r += 1
    if not prs:
        ws.cell(r, 1, "(aucune prestation)").border = border; r += 1
    last_pr = r - 1
    ws.cell(r, 1, "Sous-total prestations HT").font = Font(bold=True)
    st_pr = ws.cell(r, 4, "=SUM(D%d:D%d)" % (first_pr, last_pr)); st_pr.font = Font(bold=True); st_pr.number_format = money
    row_pr = r; r += 2

    # --- Totaux ---
    ws.cell(r, 1, "TOTAL HT").font = Font(bold=True, color=NAVY)
    tht = ws.cell(r, 5, "=E%d+D%d" % (row_mat, row_pr)); tht.font = Font(bold=True, color=NAVY); tht.number_format = money
    total_row = r; r += 1
    ws.cell(r, 1, "TVA 20%")
    tva = ws.cell(r, 5, "=E%d*0.2" % total_row); tva.number_format = money; r += 1
    ws.cell(r, 1, "TOTAL TTC").font = Font(bold=True)
    ttc = ws.cell(r, 5, "=E%d*1.2" % total_row); ttc.font = Font(bold=True); ttc.number_format = money
    r += 2
    ws.cell(r, 1, "Prix indicatifs à compléter (PU matériel, tarif/jour prestations). Valeurs en euros HT.").font = Font(italic=True, size=9, color=RED)
    wb.save(path)


@app.post("/api/chiffrage")
async def chiffrage(spec: dict):
    aff = spec.get("affaire", {}) or {}
    name = "Chiffrage_" + slug(aff.get("client") or aff.get("projet")) + "_" + \
           datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".xlsx"
    out_path = OUT_DIR / name
    try:
        build_chiffrage_xlsx(spec, str(out_path))
    except Exception as e:
        raise HTTPException(500, "Échec de la génération du chiffrage : " + str(e))
    return FileResponse(str(out_path),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename=name)


# ---------------------------------------------------------------- Cadre de mémoire technique (IA)
MEMOIRE_PROMPT = (
    "Tu remplis un CADRE DE MÉMOIRE TECHNIQUE fourni par un client dans le cadre d'un appel d'offre. "
    "On te donne (1) la TRAME du client (sections, critères notés, questions, champs à compléter) et "
    "(2) les DONNÉES DE L'AO produites par ONE ID. Produis le mémoire technique COMPLÉTÉ, en français, "
    "en respectant FIDÈLEMENT la structure, l'ordre et les intitulés de la trame. Pour chaque "
    "section/critère, rédige la réponse à partir des DONNÉES DE L'AO, en ingénieur avant-vente ONE ID, "
    "de façon claire et argumentée. "
    "RÈGLES STRICTES : ne JAMAIS inventer ; pour toute valeur non disponible dans les données fournies "
    "(ex. taux de plastique/métal recyclé, données constructeur, emballages, chiffres non présents), "
    "écris EXACTEMENT « à préciser » ; conserve les intitulés des critères et leurs points (ex. « - 20 points »). "
    "FORMAT de sortie : titres de niveau 1 préfixés par '# ', niveau 2 par '## ', niveau 3 par '### ', "
    "puces par '- '. N'ajoute aucun commentaire hors du mémoire."
)


def build_memoire_docx(client, text, path):
    import docx
    d = docx.Document()
    d.add_heading("Mémoire technique" + (" — " + client if client else ""), 0)
    for raw in (text or "").split("\n"):
        s = raw.strip().replace("**", "")
        if not s:
            continue
        if s.startswith("### "):
            d.add_heading(s[4:], 3)
        elif s.startswith("## "):
            d.add_heading(s[3:], 2)
        elif s.startswith("# "):
            d.add_heading(s[2:], 1)
        elif s[:2] in ("- ", "* "):
            d.add_paragraph(s[2:], style="List Bullet")
        else:
            d.add_paragraph(s)
    d.save(path)


@app.post("/api/memoire")
async def memoire(file: UploadFile = File(...), cctp: str = Form(""), solution: str = Form(""),
                  generated_file: str = Form(""), client: str = Form(""),
                  provider: str = Form(DEFAULT_PROVIDER), model: str = Form("")):
    fname = (file.filename or "").lower()
    if fname.endswith(".doc") and not fname.endswith(".docx"):
        raise HTTPException(400, "Format .doc non pris en charge : enregistrez la trame en .docx (ou .pdf/.txt).")
    cadre = extract_text(file.filename, await file.read()).strip()
    if not cadre:
        raise HTTPException(400, "Trame illisible : fournissez un .docx, .pdf ou .txt.")
    ao = ""
    if generated_file:
        p = OUT_DIR / Path(str(generated_file)).name
        if p.exists() and p.suffix.lower() == ".docx":
            try:
                ao = extract_docx_text(p)
            except Exception:
                ao = ""
    if not ao:
        ao = summarize_solution(solution)
    user = "CADRE DE MÉMOIRE TECHNIQUE (trame client à compléter) :\n" + cadre[:60000]
    user += "\n\nDONNÉES DE L'AO (à utiliser pour remplir) :\n" + (ao[:60000] or "(aucune)")
    if cctp.strip():
        user += "\n\nCONTEXTE CCTP :\n" + cctp[:20000]
    filled = await run_in_threadpool(llm_complete, sysp(MEMOIRE_PROMPT), user, 8000, provider, model)
    name = "Memoire_technique_" + slug(client or "client") + "_" + \
           datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".docx"
    out_path = OUT_DIR / name
    try:
        build_memoire_docx(client, filled, str(out_path))
    except Exception as e:
        raise HTTPException(500, "Échec de la génération du mémoire : " + str(e))
    return FileResponse(str(out_path),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        filename=name)


# ---------------------------------------------------------------- Génération Word
@app.post("/api/generer")
async def generer(spec: dict):
    mode = spec.pop("mode", "standard")
    ai_provider = spec.pop("ai_provider", "") or DEFAULT_PROVIDER
    ai_model = spec.pop("ai_model", "")
    if mode == "design":
        affd = spec.setdefault("affaire", {})
        try:
            d = await run_in_threadpool(design_enhance, affd, ai_provider, ai_model)
        except Exception as e:
            raise HTTPException(502, "Mode Design (moteur IA) : " + str(e))
        if d.get("intro"):
            affd["intro_override"] = d["intro"]
        if d.get("contexte"):
            affd["contexte"] = d["contexte"]
        if d.get("solution_proposee"):
            affd["solution_proposee"] = d["solution_proposee"]
        if isinstance(d.get("theme"), dict):
            spec["_theme"] = d["theme"]
    aff = spec.get("affaire", {})
    name = "AO_" + slug(aff.get("client") or aff.get("projet")) + "_" + \
           datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".docx"
    out_path = OUT_DIR / name
    with tempfile.TemporaryDirectory() as td:
        fiche = Path(td) / "fiche.json"
        fiche.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        env = dict(os.environ, BASE_DOCX=BASE_DOCX)
        r = subprocess.run([sys.executable, str(ENGINE / "generer_doc.py"),
                            str(fiche), str(out_path), DOC_BASE],
                           capture_output=True, text=True, env=env)
        if r.returncode != 0 or not out_path.exists():
            raise HTTPException(500, "Échec de la génération Word : " + (r.stderr or r.stdout)[:500])
    return FileResponse(str(out_path),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        filename=name)


# ---------------------------------------------------------------- Fiches (sauvegarde serveur)
def safe_name(name):
    base = re.sub(r"[^\w .\-]+", "_", (name or "").strip(), flags=re.UNICODE).strip(" .") or "fiche"
    base = base[:80]
    if not base.lower().endswith(".json"):
        base += ".json"
    return base


@app.post("/api/fiche/save")
async def fiche_save(payload: dict):
    spec = payload.get("spec", payload)
    aff = spec.get("affaire", {}) if isinstance(spec, dict) else {}
    nom = payload.get("name") or aff.get("client") or aff.get("projet")
    name = safe_name(nom)
    (FICHES_DIR / name).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "name": name}


@app.get("/api/fiche/list")
def fiche_list():
    items = []
    for p in sorted(FICHES_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        items.append({"name": p.name, "mtime": int(p.stat().st_mtime)})
    return {"fiches": items}


@app.get("/api/fiche/get")
def fiche_get(name: str):
    p = FICHES_DIR / safe_name(name)
    if not p.exists():
        raise HTTPException(404, "Fiche introuvable")
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.post("/api/fiche/rename")
async def fiche_rename(payload: dict):
    old = FICHES_DIR / safe_name(payload.get("old", ""))
    new = FICHES_DIR / safe_name(payload.get("new", ""))
    if not old.exists():
        raise HTTPException(404, "Fiche introuvable")
    if new.exists() and new.resolve() != old.resolve():
        raise HTTPException(409, "Une fiche porte déjà ce nom.")
    old.rename(new)
    return {"ok": True, "name": new.name}


@app.post("/api/fiche/delete")
async def fiche_delete(payload: dict):
    p = FICHES_DIR / safe_name(payload.get("name", ""))
    if p.exists():
        p.unlink()
    return {"ok": True}


# ---------------------------------------------------------------- Éditeur d'argumentaires
def safe_folder(name):
    base = re.sub(r"[^\w .\-]+", "_", (name or "").strip(), flags=re.UNICODE).strip(" .")
    return Path(base).name[:80]   # un seul segment, pas de traversée


@app.get("/api/argumentaires")
def argumentaires_list():
    base = Path(DOC_BASE)
    out = []
    if base.is_dir():
        for p in sorted(base.glob("*/argumentaire.json")):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                j = {}
            out.append({"folder": p.parent.name,
                        "titre": j.get("titre") or j.get("titre_cas") or p.parent.name,
                        "blocs": len(j.get("blocs") or [])})
    return {"items": out}


@app.get("/api/argumentaire")
def argumentaire_get(folder: str):
    p = Path(DOC_BASE) / safe_folder(folder) / "argumentaire.json"
    if not p.exists():
        raise HTTPException(404, "Argumentaire introuvable")
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.post("/api/argumentaire/save")
async def argumentaire_save(payload: dict):
    folder = safe_folder(payload.get("folder", ""))
    data = payload.get("data")
    if not folder or not isinstance(data, dict):
        raise HTTPException(400, "Requête invalide (dossier ou données manquants).")
    d = Path(DOC_BASE) / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "argumentaire.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "folder": folder}


@app.get("/api/argumentaire/images")
def argumentaire_images(folder: str):
    """Liste les fichiers image présents dans le dossier de l'argumentaire."""
    d = Path(DOC_BASE) / safe_folder(folder)
    exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
    names = []
    if d.is_dir():
        names = sorted(p.name for p in d.iterdir() if p.suffix.lower() in exts)
    return {"images": names}


@app.get("/api/argumentaire/image")
def argumentaire_image(folder: str, name: str):
    p = Path(DOC_BASE) / safe_folder(folder) / Path(name).name
    if not p.exists() or p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        raise HTTPException(404, "Image introuvable")
    return FileResponse(str(p))


# ---------------------------------------------------------------- Bibliothèques de shapes draw.io
DRAWIO_LIBS_DIR = WEB / "drawio-libs"


@app.get("/api/drawio-libs")
def drawio_libs_list():
    """Liste les bibliothèques de shapes draw.io disponibles (une par constructeur).

    Returns:
        JSON `{libs: [str]}` — noms de fichiers `.xml` (format mxlibrary), triés.

    Effets de bord : lecture du répertoire `app/web/drawio-libs/`.
    """
    libs = []
    if DRAWIO_LIBS_DIR.is_dir():
        libs = sorted(p.name for p in DRAWIO_LIBS_DIR.glob("*.xml"))
    return {"libs": libs}


@app.get("/drawio-libs/{name}")
def drawio_lib(name: str):
    """Sert une bibliothèque de shapes draw.io (fichier `.xml` mxlibrary).

    Args:
        name: nom du fichier `.xml` (le chemin est neutralisé, seul le basename compte).

    Returns:
        Le fichier XML (`application/xml`).

    Raises:
        HTTPException 404 si le fichier n'existe pas ou n'est pas un `.xml`.
    """
    p = DRAWIO_LIBS_DIR / Path(name).name
    if not p.exists() or p.suffix.lower() != ".xml":
        raise HTTPException(404, "Bibliothèque introuvable")
    # CORS : draw.io tourne sur un autre port (8081) et fetch ces libs depuis l'app (8080).
    # Origine dynamique = pas d'exposition au-delà du contexte local d'utilisation.
    return FileResponse(str(p), media_type="application/xml",
                        headers={"Access-Control-Allow-Origin": "*"})
