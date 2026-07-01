#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parseur d'export Dell Solutions Configurator (.xlsx) -> fiche de specs JSON ONE ID.

Le fichier Dell est un tableau hierarchique unique :
  - lignes d'en-tete solution (ID, Nom, Categorie, Prix...)
  - ligne de colonnes : Nom du groupe | ID groupe | Nom du produit | Quantite |
    Prix unitaire | Prix etendu | Nom du module | ID option | Nom option | Prix | SKU | Qte
  - produits (colonne "Nom du produit" renseignee)
  - composants/options de chaque produit (colonne "Nom du module" renseignee)

Sortie : JSON compatible avec generer_doc.py, categories :
  serveurs / stockages / switches / sauvegardes / logiciels_services

Usage : python3 parser_dell_excel.py entree.xlsx sortie.json
"""
import sys, json, re, datetime, unicodedata
import openpyxl


def deacc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

# Classification par mots-cles (ordre = priorite)
RULES = [
    ("logiciels_services", ["appsync", "required software", "data manager", "cloudiq", "veeam", "commvault"]),
    ("sauvegardes", ["powerprotect", "data domain", "datadomain", " dd3", " dd6", " dd9",
                     "ddos", "avamar", "networker", "cyber recovery", "ppdm",
                     "rapidrecovery", "idpa"]),
    ("switches",    ["powerswitch", "networking", "connectrix", "brocade", "switch",
                     " s5", " s4", " s3", " n3", " z9", " z10", "mx9116", "mx5108",
                     "ds-", "sfp"]),
    ("stockages",   ["powerstore", "unity", "powervault", "me5", "me4", "powerscale",
                     "isilon", "powermax", "vnx", "scv", "ecs", "objectscale",
                     "storage", "stockage", "baie"]),
    ("serveurs",    ["poweredge", "pe r", "pe t", " r6", " r7", " r8", " r9", " t1",
                     " t3", " t5", "mx740", "mx760", "mx840", "fc640", "vxrail",
                     "serveur", "server"]),
]
CAT_LABEL = {
    "serveurs": "Serveurs", "stockages": "Stockage", "switches": "Switches",
    "sauvegardes": "Baies de sauvegarde", "logiciels_services": "Logiciels & Services",
}
HARDWARE = ("serveurs", "stockages", "switches", "sauvegardes")

SPEC_HINTS = [
    ("disques", ["drive", "disque", "hard drive", "ssd", "hdd"]),
    ("memoire", ["memory", "dimm", "memoire", "ram"]),
    ("alimentation", ["power supply", "alimentation", "bloc d"]),
    ("reseau", ["mezz", "nic", "carte", "ocp", "ethernet", "gbe", " port", "sfp"]),
    ("processeur", ["processor", "processeur", "cpu", "xeon", "epyc"]),
    ("os", ["operating", "systeme", "ddos", "logiciel de base", "base logiciel"]),
    ("capacite", ["capacity", "capacite"]),
    ("support", ["prosupport", "support", "garantie", "service", "warranty"]),
]


def norm(v):
    if v is None:
        return ""
    s = str(v).replace("\n", " ").strip()
    return re.sub(r"\s+", " ", s)


def classify_text(text):
    t = " " + (text or "").lower() + " "
    for cat, kws in RULES:
        if any(k in t for k in kws):
            return cat
    return None


def classify(p):
    if isinstance(p, str):
        return classify_text(p) or "logiciels_services"
    return classify_text(p["produit"]) or classify_text(ptext(p)) or "logiciels_services"


def ptext(p):
    return p["produit"] + " " + " ".join(c["module"] for c in p["composants"])


def find_header(ws):
    for r in range(1, min(ws.max_row, 30) + 1):
        rowvals = [deacc(norm(ws.cell(r, c).value).lower()) for c in range(1, ws.max_column + 1)]
        if "nom du produit" in rowvals and "nom du module" in rowvals:
            idx = {}
            for c in range(1, ws.max_column + 1):
                v = deacc(norm(ws.cell(r, c).value).lower())
                if "nom du groupe" in v:
                    idx["groupe"] = c
                elif "nom du produit" in v:
                    idx["produit"] = c
                elif v.startswith("quantite du produit") or v == "quantite":
                    idx["qte_prod"] = c
                elif "prix unitaire" in v:
                    idx["pu"] = c
                elif "prix etendu" in v:
                    idx["pe"] = c
                elif "nom du module" in v:
                    idx["module"] = c
                elif "nom de l" in v and "option" in v:
                    idx["option"] = c
                elif v == "sku":
                    idx["sku"] = c
                elif v == "qte":
                    idx["qte_mod"] = c
                elif "prix catalogue" in v and "option" in v:
                    idx["prix_mod"] = c
            return r, idx
    raise SystemExit("En-tete Dell introuvable (colonnes 'Nom du produit'/'Nom du module').")


def fmt_qte(val, qte):
    if qte and qte not in ("", "1"):
        return val + " [qte " + str(qte) + "]"
    return val


def build_item(p, cat, qte):
    specs = {}
    for comp in p["composants"]:
        label = (comp["module"] + " " + comp["description"]).lower()
        for key, kws in SPEC_HINTS:
            if any(k in label for k in kws):
                val = comp["description"] or comp["module"]
                val = fmt_qte(val, comp.get("qte"))
                specs.setdefault(key, []).append(val)
                break
    grp = (p["groupe"] or "").strip()
    if re.match(r"(?i)^group\s*\d+$", grp):
        grp = ""
    return {
        "_source": "datasheet",
        "role": grp,
        "modele": p["produit"],
        "qte": qte,
        "prix_unitaire": p["prix_unitaire"],
        "prix_etendu": p["prix_etendu"],
        "specs_extraites": dict((k, " ; ".join(v)) for k, v in specs.items()),
        "composants": p["composants"],
    }


def parse(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    hdr, idx = find_header(ws)

    sol = {}
    for r in range(1, hdr):
        a = norm(ws.cell(r, 1).value)
        if ":" in a:
            k, _, v = a.partition(":")
            sol[k.strip().lower()] = v.strip()

    def cell(r, key):
        return norm(ws.cell(r, idx[key]).value) if key in idx else ""

    groupes = []
    current_grp = None
    current_prod = None
    for r in range(hdr + 1, ws.max_row + 1):
        grp = cell(r, "groupe")
        prod = cell(r, "produit")
        mod = cell(r, "module")
        if grp:
            current_grp = {"label": grp, "qte": cell(r, "qte_prod") or "1",
                           "prix_etendu": cell(r, "pe"), "produits": []}
            groupes.append(current_grp)
        if prod:
            if current_grp is None:
                current_grp = {"label": "", "qte": "1", "prix_etendu": "", "produits": []}
                groupes.append(current_grp)
            current_prod = {
                "produit": prod, "groupe": current_grp["label"],
                "qte": cell(r, "qte_prod") or "1",
                "prix_unitaire": cell(r, "pu"), "prix_etendu": cell(r, "pe"),
                "composants": [],
            }
            current_grp["produits"].append(current_prod)
        elif mod and current_prod is not None:
            current_prod["composants"].append({
                "module": mod, "description": cell(r, "option"),
                "sku": cell(r, "sku"), "qte": cell(r, "qte_mod"), "prix": cell(r, "prix_mod"),
            })

    buckets = dict((k, []) for k in CAT_LABEL)
    for g in groupes:
        prods = [p for p in g["produits"] if p["composants"]]
        primary = next((p for p in prods if classify(p) in HARDWARE), None)
        if primary is None and prods:
            primary = prods[0]
        for p in prods:
            cat = classify(p)
            qte = g["qte"] if (p is primary and g["qte"]) else p["qte"]
            buckets[cat].append(build_item(p, cat, qte))

    return {
        "_type": "fiche_specs_oneid", "_version": 2,
        "_import": {"source": "Dell Solutions Configurator", "fichier": path,
                    "le": datetime.date.today().isoformat()},
        "affaire": {
            "client": "", "projet": sol.get("nom de la solution", ""),
            "reference": sol.get("id de la solution", ""),
            "version": "1.0", "auteur": "", "date": datetime.date.today().isoformat(),
            "notes": sol.get("infos sur la solution", ""),
            "prix_solution": sol.get("prix catalogue de la solution", ""),
        },
        "serveurs": buckets["serveurs"],
        "stockages": buckets["stockages"],
        "switches": buckets["switches"],
        "sauvegardes": buckets["sauvegardes"],
        "logiciels_services": buckets["logiciels_services"],
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 parser_dell_excel.py entree.xlsx sortie.json")
        sys.exit(1)
    fiche = parse(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(fiche, f, ensure_ascii=False, indent=2)
    for cat in CAT_LABEL:
        items = fiche.get(cat, [])
        if items:
            print(CAT_LABEL[cat] + " : " + str(len(items)))
            for it in items:
                print("   - " + it["modele"] + " (x" + str(it["qte"]) + ") - "
                      + str(len(it["composants"])) + " composants")
    print("->", sys.argv[2])


if __name__ == "__main__":
    main()
