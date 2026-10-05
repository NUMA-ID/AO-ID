# /home/numa/projets/appel-offre/app/recap_admin.py
"""Focus administratif et contractuel (étape 3 de l'assistant AO-ID).

Module pur (aucune dépendance FastAPI ni réseau) : contrat des trois tableaux
(checklist de remise, points contractuels et financiers, questions à déposer sur
PLACE), prompt système LLM, assemblage des documents administratifs et normalisation
tolérante de la réponse du modèle. Réutilise les helpers de cellule et de statut de
``recap_cctp`` (mêmes statuts : À confirmer / À préparer / À qualifier / Validé).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from recap_cctp import A_PRECISER, MAX_ROWS, STATUTS, _cell, normalize_statut

NIVEAUX: tuple[str, ...] = ("Élevée", "Moyenne", "Faible", "À évaluer")
NIVEAU_DEFAUT = "À évaluer"
OBJECTIF = ("Objectif : sécuriser la recevabilité, les engagements contractuels et les conditions "
            "économiques avant validation du GO.")
TITRE = "Focus administratif et contractuel"
# Caractères de documents envoyés au LLM. Mesuré sur GB10 (Qwen3.8-Flash-Next, 2026-10-05) :
# 600 000 caractères = 139 596 tokens acceptés en 25 s (≈ 4,3 caractères/token en français).
# 240 000 caractères ≈ 56 000 tokens : couvre un DCE administratif courant (RC + CCAP + AE +
# annexes ≈ 180 000) en laissant de la marge. Surchargeable par RECAP_ADMIN_MAX_CHARS.
MAX_INPUT = int(os.environ.get("RECAP_ADMIN_MAX_CHARS", "240000"))
MAX_CCTP_CONTEXT = 8000  # extrait du CCTP ajouté en contexte

# Colonnes (clé JSON, libellé imposé par l'utilisateur ; « IMS » remplacé par « ONEID »).
TABLES: dict[str, dict[str, Any]] = {
    "checklist": {
        "titre": "Checklist de remise",
        "colonnes": [
            ("piece", "Pièce / exigence"),
            ("attendu_dce", "Attendu DCE"),
            ("controle_oneid", "Point de contrôle ONEID"),
            ("criticite", "Criticité"),
            ("responsable", "Responsable"),
            ("echeance", "Échéance"),
            ("statut", "Statut"),
        ],
    },
    "contractuel": {
        "titre": "Points contractuels et financiers",
        "colonnes": [
            ("theme", "Thème"),
            ("clause", "Clause / exigence"),
            ("impact_oneid", "Impact ONEID"),
            ("position", "Position recommandée"),
            ("niveau", "Niveau"),
            ("source", "Source"),
            ("statut", "Statut"),
        ],
    },
    "questions": {
        "titre": "Questions à déposer sur PLACE avant le",
        "colonnes": [
            ("num", "N°"),
            ("question", "Question proposée"),
            ("enjeu", "Enjeu"),
            ("priorite", "Priorité"),
            ("owner", "Owner"),
            ("reponse_attendue", "Réponse attendue"),
            ("statut", "Statut"),
        ],
    },
}
NIVEAU_COLS = ("criticite", "niveau", "priorite")
META_KEYS = ("reference_marche", "date_limite_questions", "date_limite_offres")
# Colonnes à fort contenu, élargies à l'écran (ADMIN_WIDE dans index.html) et dans le Word.
WIDE_COLS: tuple[str, ...] = ("attendu_dce", "controle_oneid", "clause", "impact_oneid", "position",
                              "question", "enjeu", "reponse_attendue")

# Prompt système spécifique (préfixé par le préambule ONE ID commun, voir main.sysp).
# Texte issu de l'optimisation Lyra (méthode 4-D) — voir docs/DECISIONS.md.
RECAP_ADMIN_PROMPT = r"""MISSION : produire le « Focus administratif et contractuel » à partir des documents administratifs du DCE (RC, CCAP, AE, BPU/DPGF, annexes) pour sécuriser recevabilité, engagements contractuels et conditions économiques avant le GO/NO GO.

ENTRÉE : blocs « ===== DOCUMENT : <nom de fichier> ===== » puis texte ; éventuellement « ===== CCTP (extrait, contexte) ===== », simple contexte. Le nom de fichier sert de source.

SORTIE : UNIQUEMENT un objet JSON valide. Premier caractère « { », dernier caractère « } ». Aucun texte, balise ni bloc de code autour, aucun raisonnement. Exactement ces clés, dans cet ordre :
{"reference_marche":"","date_limite_questions":"","date_limite_offres":"","checklist":[{"piece":"","attendu_dce":"","controle_oneid":"","criticite":"","responsable":"","echeance":"","statut":""}],"contractuel":[{"theme":"","clause":"","impact_oneid":"","position":"","niveau":"","source":"","statut":""}],"questions":[{"num":"","question":"","enjeu":"","priorite":"","owner":"","reponse_attendue":"","statut":""}]}

VALEURS FERMÉES (recopier exactement) :
- criticite, niveau, priorite : "Élevée", "Moyenne" ou "Faible".
- statut : "a_qualifier" (point ambigu ou contradictoire à clarifier, souvent lié à une question), "a_confirmer" (décision interne ONE ID : direction, finance, juridique, assurance) ou "a_preparer" (clair, pièce ou action à produire). N'utilise jamais "valide" : réservé à l'humain.

EN-TÊTE :
- reference_marche : référence ou numéro du marché / de la consultation tel qu'écrit, sinon "à préciser".
- date_limite_questions : date et heure limite de dépôt des questions sur la plateforme (PLACE), recopiée telle qu'écrite. Si le RC ne donne qu'un délai relatif, recopie la formulation sans calculer de date. Sinon "à préciser".
- date_limite_offres : date et heure limite de remise des offres, même règle.

CHECKLIST (8 à 20 lignes) : pièces et exigences de remise réellement citées par le DCE, candidature puis offre (DC1/DC2 ou DUME, attestations fiscales et sociales, Kbis, assurances, références, AE signé, BPU/DPGF, mémoire technique, planning, formats, signature électronique, visite obligatoire, échantillons). Aucune pièce non citée.
- piece : nom de la pièce ou exigence.
- attendu_dce : ce que le DCE demande précisément (format, contenu, signature, limite de pages).
- controle_oneid : vérification concrète à faire par ONE ID avant dépôt.
- criticite : "Élevée" si l'absence rend l'offre irrégulière ou irrecevable.
- responsable : un rôle (« Assistante ADV », « Ingénieur avant-vente », « Chef de projet », « Direction »), jamais un nom.
- echeance : date issue des documents ou échéance relative (« Avant dépôt », « J-5 avant remise »), jamais une date inventée.

CONTRACTUEL (6 à 15 lignes) : clauses à enjeu parmi durée et reconduction, forme et révision du prix, avance, retenue de garantie, délais de paiement, pénalités (montant et plafond), garanties et SLA, assurances, résiliation, propriété intellectuelle (CCAG applicable), confidentialité et RGPD, sous-traitance, critères de jugement et pondérations, variantes et PSE, clauses sociales ou environnementales, réversibilité.
- clause : ce que dit le document ; chiffres uniquement s'ils y figurent.
- impact_oneid : conséquence concrète pour ONE ID (trésorerie, risque financier, charge).
- position : posture recommandée (accepter, chiffrer le risque, poser une question, provisionner, variante si autorisée).
- niveau : niveau de risque.
- source : nom de fichier + article ou page lisible dans le texte (ex. « CCAP.pdf art. X »), sinon nom de fichier seul. N'invente jamais de numéro d'article.

QUESTIONS (3 à 10 lignes) : questions à déposer sur PLACE pour lever ambiguïtés, contradictions entre pièces ou informations manquantes (volumétrie, dates, format du BPU…).
- num : "Q1", "Q2"… dans l'ordre.
- question : formulation neutre, courtoise, directement déposable, sans révéler la stratégie de ONE ID.
- enjeu : pourquoi la réponse compte (prix, recevabilité, dimensionnement).
- owner : rôle ONE ID qui porte la question.
- reponse_attendue : type de réponse attendu de l'acheteur.

RÈGLES DE RÉDACTION :
- Chaque cellule : 1 à 3 phrases courtes, sans retour à la ligne, puce ni Markdown. Aucune chaîne vide : "à préciser".
- Guillemets doubles interdits à l'intérieur des valeurs : utilise « ».
- Une contradiction entre pièces donne une ligne "a_qualifier" et une question.
- Si seul le CCTP est fourni : produis uniquement ce qui en ressort, toutes les lignes en "a_qualifier", sans inventer.

EXEMPLES GÉNÉRIQUES — NE PAS RECOPIER, format seulement :
checklist : {"piece":"Pièce générique","attendu_dce":"Exigence telle que décrite au RC.","controle_oneid":"Vérifier présence, validité et signature.","criticite":"Élevée","responsable":"Assistante ADV","echeance":"Avant dépôt","statut":"a_preparer"}
contractuel : {"theme":"Thème générique","clause":"Clause telle que rédigée au CCAP.","impact_oneid":"Effet sur la trésorerie ou le risque.","position":"Chiffrer le risque dans l'offre.","niveau":"Moyenne","source":"NomDuFichier.pdf","statut":"a_confirmer"}
questions : {"num":"Q1","question":"Pourriez-vous préciser le point générique ?","enjeu":"Dimensionnement de l'offre.","priorite":"Élevée","owner":"Ingénieur avant-vente","reponse_attendue":"Précision chiffrée ou document complémentaire.","statut":"a_qualifier"}

AVANT D'ÉMETTRE, vérifie en silence : JSON parsable, clés exactes, nombres de lignes, valeurs fermées, aucune cellule vide, aucune date ni article inventé."""


def normalize_niveau(v: Any) -> str:
    """Ramène une criticité/niveau/priorité libre à une valeur de ``NIVEAUX``."""
    s = str(v or "").strip().lower()
    if s.startswith(("élev", "elev", "haut", "fort", "critique", "high")):
        return "Élevée"
    if s.startswith(("moy", "medium", "modér", "moder")):
        return "Moyenne"
    if s.startswith(("faib", "bas", "low")):
        return "Faible"
    return NIVEAU_DEFAUT


def _meta(v: Any) -> str:
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    return s[:200] or A_PRECISER


def normalize_admin(data: Any, allow_valide: bool = False) -> dict[str, Any]:
    """Valide et normalise un focus administratif (sortie LLM ou fiche sauvegardée).

    Garantit : métadonnées (référence, dates) non vides, les 3 tableaux présents, toutes les
    colonnes en texte non vide, statut et niveaux dans les listes autorisées, questions
    renumérotées Q1…Qn, au plus ``MAX_ROWS`` lignes par tableau.

    Args:
        data: objet décodé (dict attendu) ; toute autre forme donne des tableaux vides.
        allow_valide: True pour une saisie humaine (UI), False pour la sortie LLM.

    Returns:
        ``{reference_marche, date_limite_questions, date_limite_offres, checklist, contractuel, questions}``.
    """
    src = data if isinstance(data, dict) else {}
    out: dict[str, Any] = {k: _meta(src.get(k)) for k in META_KEYS}
    for key, spec in TABLES.items():
        out[key] = []
        rows = src.get(key)
        if not isinstance(rows, list):
            continue
        cols = [c for c, _ in spec["colonnes"]]
        content = [c for c in cols if c not in ("statut", "num") + NIVEAU_COLS]
        for row in rows:
            if not isinstance(row, dict) or not any(str(row.get(c) or "").strip() for c in content):
                continue
            clean = {c: _cell(row.get(c)) for c in cols}
            clean["statut"] = normalize_statut(row.get("statut"), allow_valide)
            for c in NIVEAU_COLS:
                if c in clean:
                    clean[c] = normalize_niveau(row.get(c))
            out[key].append(clean)
            if len(out[key]) >= MAX_ROWS:
                break
    for i, q in enumerate(out["questions"], 1):
        q["num"] = "Q%d" % i
    return out


def parse_admin(raw: str) -> dict[str, Any]:
    """Décode la réponse texte du LLM (fences, ``<think>``, texte autour tolérés).

    Returns:
        Résultat de ``normalize_admin`` + ``ok`` (False si aucun tableau extrait).
    """
    s = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    s = re.sub(r"```(?:json)?", "", s, flags=re.I).replace("```", "").strip()
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
    res = normalize_admin(data, allow_valide=False)
    return {**res, "ok": any(res[k] for k in TABLES)}


def build_user_message(docs: list[tuple[str, str]], cctp: str = "") -> str:
    """Assemble les documents administratifs pour le LLM, chacun sous un en-tête nommé.

    Le budget ``MAX_INPUT`` est réparti équitablement entre documents : un document court
    cède sa part inutilisée aux suivants, pour qu'un CCAP volumineux n'évince pas le RC.

    Args:
        docs: liste (nom de fichier, texte extrait) ; les textes vides sont ignorés.
        cctp: texte du CCTP (facultatif), ajouté tronqué à ``MAX_CCTP_CONTEXT`` en contexte.
    """
    docs = [(n, t.strip()) for n, t in docs if (t or "").strip()]
    # Répartition calculée du plus court au plus long, restitution dans l'ordre fourni.
    alloc: dict[int, int] = {}
    budget = MAX_INPUT
    order = sorted(range(len(docs)), key=lambda j: len(docs[j][1]))
    for i, j in enumerate(order):
        alloc[j] = min(len(docs[j][1]), budget // (len(docs) - i))
        budget -= alloc[j]
    parts = ["===== DOCUMENT : %s =====\n%s" % (n, t[:alloc[j]]) for j, (n, t) in enumerate(docs)]
    if (cctp or "").strip():
        parts.append("===== CCTP (extrait, contexte) =====\n" + cctp.strip()[:MAX_CCTP_CONTEXT])
    return "\n\n".join(parts)


def statut_label(key: str) -> str:
    """Libellé affiché d'une clé de statut (identique au focus technique)."""
    return STATUTS.get(key, key)


_DATE_RE = re.compile(r"\d{1,2}/\d{1,2}/\d{2,4}(?:\s*(?:à|a|-)?\s*\d{1,2}\s*[hH:]\s*\d{0,2})?")


def date_courte(v: str) -> str:
    """Extrait « jj/mm/aaaa [à hh h mm] » d'une date commentée par le LLM, pour un titre.

    Ex. « 05/10/2026 à 12h00 (plateforme PLACE, RC Art. 3) » → « 05/10/2026 à 12h00 ».
    Sans date reconnaissable (délai relatif, « à préciser »), renvoie la valeur inchangée.
    """
    m = _DATE_RE.search(v or "")
    return m.group(0).strip() if m else (v or A_PRECISER)
