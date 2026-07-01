#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Appel d'offre ONE ID — backend FastAPI.
Tout-en-un : analyse CCTP via l'API Claude, import Excel Dell, génération du Word ONE ID.
"""
import os, json, tempfile, subprocess, sys, datetime, re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine"
WEB = HERE / "web"
ASSETS = HERE / "assets"

BASE_DOCX = os.environ.get("BASE_DOCX", str(ASSETS / "TEMPLATE_BASE_ONEID.docx"))
DOC_BASE = os.environ.get("DOC_BASE", str(HERE.parent / "Documentation_Constructeur"))
OUT_DIR = Path(os.environ.get("OUT_DIR", str(HERE.parent / "Documents_Generes")))
FICHES_DIR = Path(os.environ.get("FICHES_DIR", str(HERE.parent / "Fiches_Specs")))
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

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


MAMMOUTH_API_KEY = os.environ.get("MAMMOUTH_API_KEY", "")
MAMMOUTH_BASE = os.environ.get("MAMMOUTH_BASE", "https://api.mammouth.ai/v1")


def llm_complete(system, user, max_tokens=4000, provider="claude", model=""):
    """Appelle le moteur IA choisi : 'claude' (Anthropic) ou 'mammouth' (OpenAI-compatible)."""
    provider = (provider or "claude").lower()
    if provider == "mammouth":
        if not MAMMOUTH_API_KEY:
            raise HTTPException(400, "MAMMOUTH_API_KEY non configurée (voir fichier .env).")
        import urllib.request, urllib.error
        body = json.dumps({
            "model": model or "mistral", "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode("utf-8")
        req = urllib.request.Request(
            MAMMOUTH_BASE.rstrip("/") + "/chat/completions", data=body,
            headers={"Authorization": "Bearer " + MAMMOUTH_API_KEY,
                     "Content-Type": "application/json",
                     "Accept": "application/json",
                     "User-Agent": "ONEID-AO/1.0 (+https://one-id.fr)"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            return d["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                detail = ""
            raise HTTPException(502, "Erreur API Mammouth (HTTP %s) : %s" % (e.code, detail or e.reason))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, "Erreur API Mammouth : " + str(e))
    # défaut : Claude (Anthropic)
    if not API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY non configurée (voir fichier .env).")
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=API_KEY)
        msg = client.messages.create(model=model or MODEL, max_tokens=max_tokens, system=system,
                                     messages=[{"role": "user", "content": user}])
        return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, "Erreur API Claude : " + str(e))

OUT_DIR.mkdir(parents=True, exist_ok=True)
FICHES_DIR.mkdir(parents=True, exist_ok=True)

APP_VERSION = "2.0"


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
def index():
    f = WEB / "index.html"
    if not f.exists():
        return HTMLResponse("<h1>Frontend manquant</h1>", status_code=500)
    html = f.read_text(encoding="utf-8").replace("__BUILD__", _build_stamp())
    return HTMLResponse(html)


@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL, "api_key_set": bool(API_KEY),
            "doc_base": DOC_BASE, "out_dir": str(OUT_DIR)}


# ---------------------------------------------------------------- Extraction texte
def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="replace")
    if name.endswith(".docx"):
        import docx, io
        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs)
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
    return "\n".join(lines)


@app.post("/api/analyse-cctp")
async def analyse_cctp(file: UploadFile = File(None), text: str = Form(None), solution: str = Form(None),
                       provider: str = Form("claude"), model: str = Form("")):
    cctp = ""
    if file is not None:
        cctp = extract_text(file.filename, await file.read())
    elif text:
        cctp = text
    cctp = (cctp or "").strip()
    if not cctp:
        raise HTTPException(400, "CCTP vide : fournissez un fichier (PDF/Word/TXT) ou du texte.")
    sol_summary = summarize_solution(solution)
    user = "TEXTE DU CCTP :\n\n" + cctp[:120000]
    if sol_summary:
        user += "\n\nSOLUTION ACTUELLEMENT CONFIGURÉE :\n" + sol_summary[:20000]
    else:
        user += "\n\n(Aucune solution configurée pour le moment : marque les exigences en 'a_preciser'.)"
    raw = llm_complete(sysp(CCTP_PROMPT), user, 8000, provider, model)

    # Nettoyage des éventuelles balises markdown ```json ... ```
    cleaned = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if m:
        cleaned = m.group(1).strip()
    data = parse_json_loose(cleaned) or {}
    contexte = (data.get("contexte") or "").strip()
    points = data.get("points") or []
    clarifications = data.get("clarifications") or []
    verification = data.get("verification") or []
    # Repli : si le JSON n'a pas pu être exploité, on renvoie au moins le texte brut
    if not contexte and not points:
        contexte = raw.strip()
    return {"contexte": contexte, "points": points,
            "clarifications": clarifications, "verification": verification, "cctp_text": cctp,
            "raw": "" if (contexte or points) and parse_json_loose(cleaned) else raw}


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
    raw = llm_complete(sysp(CHAP_PROMPT), user, 4000, payload.get("provider"), payload.get("model"))
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
    sol = summarize_solution(payload.get("solution"))
    user = "TEXTE DU CCTP :\n\n" + cctp[:120000]
    user += ("\n\nSOLUTION ACTUELLEMENT CONFIGURÉE :\n" + sol[:20000]) if sol else \
            "\n\n(Aucune solution configurée : marque les exigences en 'a_preciser'.)"
    raw = llm_complete(sysp(VERIF_PROMPT), user, 6000, payload.get("provider"), payload.get("model"))
    cleaned = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if m:
        cleaned = m.group(1).strip()
    data = parse_json_loose(cleaned) or {}
    return {"verification": data.get("verification") or []}


# ---------------------------------------------------------------- Mode Design (API Claude)
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


def design_enhance(aff: dict, provider="claude", model="") -> dict:
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
    out = llm_complete(sysp(SOLUTION_PROMPT), user, 3000, payload.get("provider"), payload.get("model")).strip()
    return {"text": out}


# ---------------------------------------------------------------- Génération Word
@app.post("/api/generer")
async def generer(spec: dict):
    mode = spec.pop("mode", "standard")
    ai_provider = spec.pop("ai_provider", "claude")
    ai_model = spec.pop("ai_model", "")
    if mode == "design":
        affd = spec.setdefault("affaire", {})
        try:
            d = design_enhance(affd, ai_provider, ai_model)
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
