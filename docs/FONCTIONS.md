# Fonctions et endpoints exposés — Générateur d'appel d'offre ONE ID

Toutes les routes sont exposées par `app/main.py` (FastAPI). Sauf mention contraire,
les entrées `payload: dict` sont des corps JSON bruts (pas de modèle Pydantic défini).

---

## `GET /`
**Rôle** : sert la page HTML unique de l'application (frontend SPA).
**Entrées** : aucune.
**Sortie** : `HTMLResponse` — contenu de `app/web/index.html`, avec le marqueur
`__BUILD__` remplacé par la date de build calculée (mtime la plus récente parmi
`index.html`, `main.py`, `generer_doc.py`).
**Erreurs possibles** : `500` si `app/web/index.html` est absent ("Frontend manquant").
**Effets de bord** : lecture disque (`web/index.html`).

## `GET /api/health`
**Rôle** : sonde de santé / diagnostic de configuration.
**Entrées** : aucune.
**Sortie** : JSON `{ok, model, api_key_set, doc_base, out_dir}`.
**Erreurs possibles** : aucune.
**Effets de bord** : aucun.

## `POST /api/analyse-cctp`
**Rôle** : analyse un CCTP (fichier ou texte) via le moteur IA et en extrait contexte,
points d'attention, clarifications et grille de vérification préliminaire.
**Entrées** :
- `file: UploadFile` (optionnel, PDF/Word/TXT)
- `text: str` (optionnel, texte brut du CCTP)
- `solution: str` (optionnel, JSON sérialisé de la solution déjà configurée)
- `provider: str` (défaut : `DEFAULT_PROVIDER` = `gb10` ; seul `gb10` desservi depuis le 2026-09-09)
- `model: str` (optionnel)
**Sortie** : JSON `{contexte, points, clarifications, verification, cctp_text, raw}`.
**Erreurs possibles** : `400` si aucun CCTP fourni (fichier et texte vides) ; `400`/`502`
propagés par `llm_complete` si clé API manquante ou erreur amont.
**Effets de bord** : appel réseau sortant vers le serveur vLLM GB10 (`GB10_BASE`).

## `POST /api/import-excel`
**Rôle** : convertit un export Dell Solutions Configurator OU un devis distributeur
TD SYNNEX (.xlsx) en fiche JSON classée par catégorie d'équipement (auto-détection du
format par les colonnes d'en-tête présentes).
**Entrées** : `file: UploadFile` (obligatoire, .xlsx).
**Sortie** : JSON de la fiche classée (serveurs/stockages/switches/sauvegardes/logiciels).
**Erreurs possibles** : `500` si le sous-processus `parser_dell_excel.py` échoue (retour
non nul ou fichier de sortie absent, y compris si aucun des deux formats reconnus n'est
détecté) — message tronqué à 500 caractères côté réponse HTTP ; le traceback complet est
loggé côté serveur (stdout du conteneur) depuis le 2026-08-24.
**Effets de bord** : écriture disque temporaire (répertoire `tempfile.TemporaryDirectory`,
auto-nettoyé), exécution d'un sous-processus Python.

## `POST /api/proposer-chapitres`
**Rôle** : regroupe une liste de points d'attention (issus du CCTP) en chapitres
thématiques proposés pour le mémoire technique, via le moteur IA.
**Entrées** : `payload: dict` — `{points: [str], provider?, model?}`.
**Sortie** : JSON `{chapitres: [{titre, cartes: [str]}]}`.
**Erreurs possibles** : `400` si `points` est vide ou absent.
**Effets de bord** : appel réseau sortant vers le moteur IA choisi.

## `POST /api/verifier`
**Rôle** : compare les exigences du CCTP au contenu de l'AO déjà généré (ou, à défaut,
au résumé de la solution configurée) et produit une grille de conformité.
**Entrées** : `payload: dict` — `{cctp_text: str, generated_file?: str, solution?: str,
provider?, model?}`.
**Sortie** : JSON `{verification: [{theme, exigence, statut, suggestion}]}`.
**Erreurs possibles** : `400` si `cctp_text` est vide.
**Effets de bord** : lecture disque du `.docx` généré si `generated_file` est fourni
(dans `OUT_DIR`) ; appel réseau sortant vers le moteur IA.

## `POST /api/ameliorer-solution`
**Rôle** : reformule un texte de description de solution en argumentaire commercial
fluide, sans ajouter de fait non fourni.
**Entrées** : `payload: dict` — `{text: str, client?, projet?, provider?, model?}`.
**Sortie** : JSON `{text: str}` (texte réécrit).
**Erreurs possibles** : `400` si `text` est vide.
**Effets de bord** : appel réseau sortant vers le moteur IA.

## `POST /api/chiffrage`
**Rôle** : génère un classeur Excel de chiffrage (matériel + prestations, sous-totaux,
TVA, total TTC) à partir de la fiche de specs.
**Entrées** : `spec: dict` (fiche de specs complète).
**Sortie** : `FileResponse` — fichier `.xlsx` téléchargeable, nommé
`Chiffrage_<slug_client>_<horodatage>.xlsx`.
**Erreurs possibles** : `500` si `build_chiffrage_xlsx` lève une exception.
**Effets de bord** : écriture disque dans `OUT_DIR` (`Documents_Generes/`), persistante
(non nettoyée automatiquement).

## `POST /api/memoire`
**Rôle** : remplit le cadre de mémoire technique fourni par le client (trame) à partir
des données de l'AO déjà produites, via le moteur IA, puis génère un `.docx`.
**Entrées** :
- `file: UploadFile` (obligatoire, trame `.docx`/`.pdf`/`.txt` — `.doc` refusé)
- `cctp: str` (optionnel, contexte CCTP)
- `solution: str` (optionnel, JSON de la solution)
- `generated_file: str` (optionnel, nom du `.docx` d'AO déjà généré, dans `OUT_DIR`)
- `client: str` (optionnel)
- `provider`, `model` (optionnels)
**Sortie** : `FileResponse` — fichier `.docx`, nommé
`Memoire_technique_<slug_client>_<horodatage>.docx`.
**Erreurs possibles** : `400` si extension `.doc` (non `.docx`) ou trame illisible ;
`500` si `build_memoire_docx` échoue.
**Effets de bord** : lecture disque du `.docx` d'AO si fourni ; appel réseau sortant vers
le moteur IA ; écriture disque dans `OUT_DIR`.

## `POST /api/generer`
**Rôle** : génère le mémoire technique Word final (document d'appel d'offre) à partir de
la fiche de specs complète, avec un mode optionnel "Design" (réécriture IA de
l'intro/contexte/solution + thème de couleur).
**Entrées** : `spec: dict` — fiche de specs complète, avec clés optionnelles `mode`
("standard" ou "design"), `ai_provider`, `ai_model`.
**Sortie** : `FileResponse` — fichier `.docx`, nommé
`AO_<slug_client>_<horodatage>.docx`.
**Erreurs possibles** : `502` si le mode Design échoue (appel IA) ; `500` si le
sous-processus `generer_doc.py` échoue (retour non nul ou fichier de sortie absent).
**Effets de bord** : en mode Design, appel réseau sortant vers le moteur IA ; écriture
disque temporaire (fiche JSON) ; exécution d'un sous-processus Python
(`generer_doc.py`) qui lit `Documentation_Constructeur/` et le template
`assets/TEMPLATE_BASE_ONEID.docx` ; écriture finale dans `Documents_Generes/`.

## `POST /api/fiche/save`
**Rôle** : sauvegarde la fiche de specs courante dans l'historique serveur.
**Entrées** : `payload: dict` — `{spec: dict, name?: str}` (ou directement le spec si
`spec` absent).
**Sortie** : JSON `{ok: true, name: str}` (nom de fichier réellement utilisé, assaini).
**Erreurs possibles** : aucune levée explicitement (écrit toujours, nom de repli
`"fiche.json"` si aucun nom déductible).
**Effets de bord** : écriture disque dans `FICHES_DIR` (`Fiches_Specs/<name>.json`),
écrase un fichier existant du même nom sans confirmation.

## `GET /api/fiche/list`
**Rôle** : liste les fiches de specs sauvegardées, triées par date de modification
décroissante.
**Entrées** : aucune.
**Sortie** : JSON `{fiches: [{name, mtime}]}`.
**Erreurs possibles** : aucune.
**Effets de bord** : lecture disque (listing de `FICHES_DIR`).

## `GET /api/fiche/get`
**Rôle** : récupère le contenu JSON d'une fiche sauvegardée.
**Entrées** : `name: str` (query param).
**Sortie** : JSON du contenu de la fiche.
**Erreurs possibles** : `404` si la fiche n'existe pas.
**Effets de bord** : lecture disque.

## `POST /api/fiche/rename`
**Rôle** : renomme une fiche existante.
**Entrées** : `payload: dict` — `{old: str, new: str}`.
**Sortie** : JSON `{ok: true, name: str}` (nouveau nom assaini).
**Erreurs possibles** : `404` si l'ancienne fiche n'existe pas ; `409` si une fiche du
nouveau nom existe déjà (et diffère de l'ancienne).
**Effets de bord** : renommage sur disque (`Path.rename`).

## `POST /api/fiche/delete`
**Rôle** : supprime une fiche sauvegardée.
**Entrées** : `payload: dict` — `{name: str}`.
**Sortie** : JSON `{ok: true}` (idempotent : pas d'erreur si le fichier n'existe pas).
**Erreurs possibles** : aucune levée explicitement.
**Effets de bord** : suppression disque définitive, sans confirmation ni corbeille.

## `GET /api/argumentaires`
**Rôle** : liste les argumentaires produits disponibles dans `Documentation_Constructeur/`.
**Entrées** : aucune.
**Sortie** : JSON `{items: [{folder, titre, blocs}]}`.
**Erreurs possibles** : aucune (fichiers JSON illisibles silencieusement ignorés →
traités comme vides).
**Effets de bord** : lecture disque (parcours de `DOC_BASE`).

## `GET /api/argumentaire`
**Rôle** : récupère le contenu JSON d'un argumentaire donné.
**Entrées** : `folder: str` (query param, nom de dossier).
**Sortie** : JSON du contenu de `argumentaire.json`.
**Erreurs possibles** : `404` si l'argumentaire n'existe pas.
**Effets de bord** : lecture disque.

## `POST /api/argumentaire/save`
**Rôle** : crée ou met à jour un argumentaire (texte/blocs/images de référence).
**Entrées** : `payload: dict` — `{folder: str, data: dict}`.
**Sortie** : JSON `{ok: true, folder: str}`.
**Erreurs possibles** : `400` si `folder` vide ou `data` n'est pas un objet.
**Effets de bord** : création de dossier + écriture disque dans
`DOC_BASE/<folder>/argumentaire.json` (écrase le contenu existant).

## `GET /api/argumentaire/images`
**Rôle** : liste les fichiers image présents dans le dossier d'un argumentaire.
**Entrées** : `folder: str` (query param).
**Sortie** : JSON `{images: [str]}` (noms de fichiers, extensions
png/jpg/jpeg/gif/webp).
**Erreurs possibles** : aucune (dossier absent → liste vide).
**Effets de bord** : lecture disque (listing de répertoire).

## `GET /api/argumentaire/image`
**Rôle** : sert le contenu binaire d'une image d'argumentaire.
**Entrées** : `folder: str`, `name: str` (query params).
**Sortie** : `FileResponse` (image brute).
**Erreurs possibles** : `404` si le fichier n'existe pas ou si son extension n'est pas
une image reconnue.
**Effets de bord** : lecture disque. Le nom de fichier est réduit à `Path(name).name`
pour éviter la traversée de répertoire.

## `GET /api/drawio-libs`
**Rôle** : liste les bibliothèques de shapes draw.io ONE ID disponibles (une par constructeur).
**Entrées** : aucune.
**Sortie** : JSON `{libs: [str]}` — noms de fichiers `.xml` (format `mxlibrary`), triés.
**Erreurs possibles** : aucune (liste vide si le répertoire est absent).
**Effets de bord** : lecture du répertoire `app/web/drawio-libs/`.

## `GET /drawio-libs/{name}`
**Rôle** : sert une bibliothèque de shapes draw.io (fichier `.xml` `mxlibrary`), chargée
automatiquement dans l'éditeur via le paramètre `clibs` de l'URL draw.io.
**Entrées** : `name: str` (segment de chemin ; réduit à `Path(name).name`).
**Sortie** : `FileResponse` `application/xml`, avec en-tête `Access-Control-Allow-Origin: *`
(draw.io sur le port 8081 fetch depuis le port 8080 — requête cross-origin).
**Erreurs possibles** : `404` si le fichier n'existe pas ou n'est pas un `.xml`.
**Effets de bord** : lecture disque. Traversée de répertoire neutralisée (`Path(name).name`).

---

## Fonctions internes notables (non exposées en HTTP)

| Fonction | Fichier | Rôle | Effets de bord |
|---|---|---|---|
| `llm_complete(system, user, max_tokens, provider, model)` | main.py | Point d'entrée unique vers les moteurs IA (Claude, Mammouth, Mistral ou GB10) | Appel réseau sortant |
| `extract_text(filename, data)` | main.py | Extraction de texte depuis .txt/.docx/.pdf | Aucun (traitement en mémoire) |
| `extract_docx_text(path)` | main.py | Extraction texte + tableaux d'un .docx généré | Lecture disque |
| `parse_cctp(raw)` | main.py | Parsing tolérant du JSON renvoyé par l'IA (fallback regex si JSON malformé) | Aucun |
| `summarize_solution(sol)` | main.py | Résumé textuel de la solution configurée (pour comparaison CCTP) | Aucun |
| `build_chiffrage_xlsx(spec, path)` | main.py | Construction du classeur Excel de chiffrage | Écriture disque |
| `build_memoire_docx(client, text, path)` | main.py | Construction du .docx de mémoire technique depuis un texte structuré (titres `#`/`##`/`###`, listes `-`) | Écriture disque |
| `generer_doc.py` (script complet) | app/engine/ | Génération du document Word principal (voir en-tête du fichier) | Écriture disque, lecture de `Documentation_Constructeur/` et du template |
| `parser_dell_excel.py` (script complet) | app/engine/ | Parsing de l'export Dell → JSON classé | Lecture du .xlsx fourni |
