# /home/numa/projets/appel-offre/app/recap_cctp.py
"""Récapitulatif du CCTP — Focus technique (étape 2 de l'assistant AO-ID).

Module pur (aucune dépendance FastAPI ni réseau) : contrat des trois tableaux,
prompt système LLM et normalisation tolérante de la réponse du modèle.
Consommé par ``main.py`` (endpoint ``/api/recap-cctp``) et, pour les libellés,
par ``engine/generer_doc.py`` (export Word).
"""
from __future__ import annotations

import json
import re
from typing import Any

# Statuts autorisés (clé technique -> libellé affiché). « valide » est réservé à l'humain :
# toute valeur « valide » renvoyée par le LLM est rétrogradée en « a_confirmer ».
STATUTS: dict[str, str] = {
    "a_confirmer": "À confirmer",
    "a_preparer": "À préparer",
    "a_qualifier": "À qualifier",
    "valide": "Validé",
}
STATUT_DEFAUT = "a_confirmer"
GO_NOGO = ("Go", "No Go", "À arbitrer")
A_PRECISER = "à préciser"
MAX_CELL = 600      # caractères max par cellule (lisibilité du tableau Word)
MAX_ROWS = 30       # lignes max par tableau (garde-fou contre une sortie divergente)

# Ordre des colonnes = ordre d'affichage (UI + Word). (clé JSON, libellé imposé par l'utilisateur)
TABLES: dict[str, dict[str, Any]] = {
    "matrice": {
        "titre": "Matrice de couverture technique",
        "colonnes": [
            ("domaine", "Domaine"),
            ("exigences", "Exigences principales"),
            ("preuves", "Attendus de preuve dans l'offre"),
            ("capacite_oneid", "Capacité ONEID à confirmer"),
            ("risque", "Risque"),
            ("action", "Action de réponse"),
            ("ref", "Réf."),
            ("statut", "Statut"),
        ],
    },
    "plan": {
        "titre": "Plan de prise en charge recommandé",
        "colonnes": [
            ("periode", "Période"),
            ("objectifs", "Objectifs"),
            ("actions", "Actions / livrables"),
            ("criteres", "Critères de réussite"),
            ("contribution_note", "Contribution à la note"),
            ("pilote", "Pilote"),
            ("risque", "Risque à maîtriser"),
            ("statut", "Statut"),
        ],
    },
    "ressources": {
        "titre": "Ressources minimales à proposer",
        "colonnes": [
            ("role", "Rôle"),
            ("responsabilite", "Responsabilité"),
            ("competences", "Compétences attendues"),
            ("presence", "Exigence de présence"),
            ("preuve", "Preuve à joindre"),
            ("backup", "Back-up"),
            ("go_nogo", "Go / No Go"),
            ("statut", "Statut"),
        ],
    },
}

# Colonnes à fort contenu, élargies à l'écran (RECAP_WIDE dans index.html) et dans le Word.
WIDE_COLS: tuple[str, ...] = ("exigences", "preuves", "capacite_oneid", "risque", "action",
                              "objectifs", "actions", "criteres", "responsabilite", "competences",
                              "preuve")

# Prompt système spécifique (préfixé à l'appel par le préambule ONE ID commun, voir main.sysp).
# Texte issu de l'optimisation Lyra (méthode 4-D) — voir docs/DECISIONS.md.
RECAP_PROMPT = r"""TÂCHE : à partir du CCTP fourni, produire le « Récapitulatif du CCTP — Focus technique » du mémoire technique, en 3 tableaux : matrice de couverture technique, plan de prise en charge recommandé, ressources minimales à proposer.

ENTRÉES : seul le « TEXTE DU CCTP » fait foi pour les exigences. « POINTS D'ATTENTION », « CLARIFICATIONS » et « SOLUTION ACTUELLEMENT CONFIGURÉE », s'ils sont présents, servent à préciser risques et actions, jamais à affirmer une capacité de ONE ID.

FORMAT DE SORTIE — IMPÉRATIF
Réponds UNIQUEMENT par un objet JSON valide, du premier « { » au dernier « } ». Aucun texte, raisonnement ni bloc ``` autour. Structure exacte, aucune clé ajoutée ni omise :
{"matrice":[{"domaine":"","exigences":"","preuves":"","capacite_oneid":"","risque":"","action":"","ref":"","statut":""}],"plan":[{"periode":"","objectifs":"","actions":"","criteres":"","contribution_note":"","pilote":"","risque":"","statut":""}],"ressources":[{"role":"","responsabilite":"","competences":"","presence":"","preuve":"","backup":"","go_nogo":"","statut":""}]}
Chaque valeur : chaîne NON VIDE (info absente = « à préciser »), 1 à 3 phrases courtes, sans retour à la ligne, puce ni Markdown. Guillemets doubles, guillemets internes échappés (\"), pas de virgule finale.

1. "matrice" (6 à 15 lignes) : une ligne par grand domaine technique RÉELLEMENT présent dans le CCTP (serveurs/stockage, sauvegarde/PRA-PCA, réseau, sécurité, virtualisation, licences, migration, support/garantie/MCO, RGPD/ANSSI, réversibilité…). Aucun domaine absent.
- exigences : reformulation fidèle, chiffres du CCTP uniquement.
- preuves : pièces démontrant la conformité (fiche technique, certificat, attestation, référence, schéma, planning, BPU/DPGF).
- capacite_oneid : commence par « À confirmer : » puis ce que ONE ID doit confirmer (certification, partenariat, compétence, référence client).
- risque : commence par « Élevé : », « Moyen : » ou « Faible : » puis une justification courte.
- action : réponse à rédiger dans le mémoire technique ou question à poser à l'acheteur.
- ref : article, chapitre ou page lisible dans le CCTP (ex. « CCTP §4.2 »), sinon « à préciser ». N'invente jamais de numéro.

2. "plan" (3 à 6 lignes, ordre chronologique)
- periode : phase relative (« Phase 0 — Remise de l'offre », « M0 → M1 — Lancement », « Run / MCO ») ; dates seulement si le CCTP en donne.
- actions : actions et livrables. criteres : critères de réussite vérifiables.
- contribution_note : critère de jugement visé (valeur technique, prix, délais…) et pondération SEULEMENT si le CCTP ou le RC cité les mentionne, sinon « à préciser ».
- pilote : un rôle (« Chef de projet ONE ID », « Ingénieur avant-vente »), jamais un nom.

3. "ressources" (3 à 8 lignes) : profils exigés par le CCTP ou, à défaut, déduits des exigences (statut "a_qualifier").
- competences : certifications ou niveaux seulement s'ils sont cités.
- presence : sur site, astreinte, délai d'intervention tels que cités, sinon « à préciser ».
- preuve : pièce à joindre (CV, certificat, attestation). backup : remplacement exigé ou à prévoir.
- go_nogo : exactement « Go », « No Go » ou « À arbitrer » (« À arbitrer » si disponibilité ou compétence non établie).

"statut" (chaque ligne) : exactement une de ces valeurs.
- "a_qualifier" : info du CCTP ambiguë, incomplète ou contradictoire, à qualifier avec l'acheteur.
- "a_confirmer" : ONE ID semble pouvoir répondre, capacité ou ressource à confirmer en interne.
- "a_preparer" : exigence claire, preuve ou livrable à produire.
Toute autre valeur est interdite : la validation est réservée à l'humain.

EXEMPLE ILLUSTRATIF — générique, NE PAS RECOPIER :
{"domaine":"Sauvegarde","exigences":"Sauvegarde quotidienne externalisée, rétention fixée par le CCTP.","preuves":"Fiche technique, procédure de restauration.","capacite_oneid":"À confirmer : référence client sur la solution proposée.","risque":"Moyen : volumétrie non précisée.","action":"Demander la volumétrie à l'acheteur.","ref":"à préciser","statut":"a_qualifier"}
{"periode":"Phase 0 — Remise de l'offre","objectifs":"Lever les ambiguïtés du CCTP.","actions":"Questions écrites, schéma cible.","criteres":"Réponses obtenues avant la date limite.","contribution_note":"à préciser","pilote":"Ingénieur avant-vente","risque":"Hypothèses non validées.","statut":"a_preparer"}
{"role":"Chef de projet","responsabilite":"Pilotage et planning.","competences":"Gestion de projet d'infrastructure.","presence":"à préciser","preuve":"CV","backup":"à préciser","go_nogo":"À arbitrer","statut":"a_confirmer"}

CONTRÔLE AVANT ENVOI (sans l'écrire) : JSON parsable, 3 clés racine, toutes les clés sur chaque ligne, aucune chaîne vide, statut et go_nogo conformes, aucun chiffre, référence ou capacité absent des entrées."""

_FENCE = re.compile(r"```(?:json)?", re.I)


def _cell(v: Any) -> str:
    """Convertit une valeur LLM en texte de cellule : une ligne, bornée, jamais vide."""
    if v is None:
        s = ""
    elif isinstance(v, (list, tuple)):
        s = " ; ".join(str(x).strip() for x in v if str(x).strip())
    elif isinstance(v, dict):
        s = " ; ".join("%s : %s" % (k, x) for k, x in v.items())
    else:
        s = str(v)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > MAX_CELL:
        s = s[: MAX_CELL - 1].rstrip() + "…"
    return s or A_PRECISER


def normalize_statut(v: Any, allow_valide: bool = False) -> str:
    """Ramène un statut libre (clé ou libellé, accents/casse indifférents) à une clé de STATUTS.

    Args:
        v: valeur brute (« À confirmer », « a_preparer », « Validé »…).
        allow_valide: True quand la valeur vient de l'humain (UI) ; False pour la sortie LLM,
            auquel cas « valide » est rétrogradé en ``STATUT_DEFAUT``.

    Returns:
        Une clé de ``STATUTS`` ; ``STATUT_DEFAUT`` si la valeur est inconnue.
    """
    s = str(v or "").strip().lower()
    for a, b in (("à", "a"), ("é", "e"), ("è", "e"), (" ", "_"), ("-", "_")):
        s = s.replace(a, b)
    if s in STATUTS:
        key = s
    elif s.startswith("valid"):
        key = "valide"
    else:
        key = next((k for k in STATUTS if k != "valide" and k in s), STATUT_DEFAUT)
    if key == "valide" and not allow_valide:
        return STATUT_DEFAUT
    return key


def _normalize_go(v: Any) -> str:
    s = str(v or "").strip().lower().replace("-", " ")
    if s in ("go", "oui", "yes"):
        return "Go"
    if s.replace(" ", "") in ("nogo",) or s in ("no go", "non"):
        return "No Go"
    return "À arbitrer"


def normalize_recap(data: Any, allow_valide: bool = False) -> dict[str, list[dict[str, str]]]:
    """Valide et normalise un récapitulatif (sortie LLM ou fiche sauvegardée).

    Garantit : les 3 clés de ``TABLES`` présentes, chaque ligne avec toutes ses colonnes
    en texte non vide, statut et Go/No Go dans les listes autorisées, au plus ``MAX_ROWS``
    lignes par tableau. Les lignes non-dict ou entièrement vides sont écartées.

    Args:
        data: objet décodé (dict attendu) ; toute autre forme donne 3 tableaux vides.
        allow_valide: voir ``normalize_statut``.

    Returns:
        ``{"matrice": [...], "plan": [...], "ressources": [...]}``.
    """
    out: dict[str, list[dict[str, str]]] = {k: [] for k in TABLES}
    if not isinstance(data, dict):
        return out
    for key, spec in TABLES.items():
        rows = data.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            cols = [c for c, _ in spec["colonnes"] if c not in ("statut", "go_nogo")]
            if not any(str(row.get(c) or "").strip() for c in cols):
                continue
            clean = {c: _cell(row.get(c)) for c, _ in spec["colonnes"]}
            clean["statut"] = normalize_statut(row.get("statut"), allow_valide)
            if "go_nogo" in clean:
                clean["go_nogo"] = _normalize_go(row.get("go_nogo"))
            out[key].append(clean)
            if len(out[key]) >= MAX_ROWS:
                break
    return out


def parse_recap(raw: str) -> dict[str, Any]:
    """Décode la réponse texte du LLM en récapitulatif normalisé.

    Tolère les fences Markdown, du texte autour de l'objet JSON et les balises
    ``<think>…</think>`` résiduelles.

    Returns:
        ``{"matrice", "plan", "ressources", "ok"}`` ; ``ok`` est False si aucun
        tableau n'a pu être extrait (le texte brut est alors à remonter à l'UI).
    """
    s = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    s = _FENCE.sub("", s).replace("```", "").strip()
    data: Any = None
    try:
        data = json.loads(s)
    except Exception:
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            try:
                data = json.loads(s[a: b + 1])
            except Exception:
                data = None
    rec = normalize_recap(data, allow_valide=False)
    rec_ok = any(rec[k] for k in TABLES)
    return {**rec, "ok": rec_ok}


def build_user_message(cctp: str, points: list[Any] | None = None,
                       clarifications: list[Any] | None = None, solution_summary: str = "") -> str:
    """Construit le message utilisateur envoyé au LLM (sections absentes omises).

    Le CCTP est tronqué à 60 000 caractères (même budget que /api/analyse-cctp,
    contrainte de la passerelle Bifrost à 300 s).
    """
    msg = "TEXTE DU CCTP :\n\n" + (cctp or "")[:60000]
    pts = [str(p.get("label") if isinstance(p, dict) else p).strip() for p in (points or [])]
    pts = [p for p in pts if p and p != "None"]
    if pts:
        msg += "\n\nPOINTS D'ATTENTION DÉJÀ IDENTIFIÉS :\n" + "\n".join("- " + p for p in pts)[:8000]
    cls = [str(c).strip() for c in (clarifications or []) if str(c).strip()]
    if cls:
        msg += "\n\nCLARIFICATIONS :\n" + "\n".join("- " + c for c in cls)[:6000]
    if (solution_summary or "").strip():
        msg += "\n\nSOLUTION ACTUELLEMENT CONFIGURÉE :\n" + solution_summary[:15000]
    return msg
