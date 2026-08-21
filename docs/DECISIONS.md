# Décisions techniques — Générateur d'appel d'offre ONE ID

## 2026-06-01 — Application locale Docker, pas de SaaS
Choix d'une application 100 % locale (Docker Desktop), sans hébergement distant à ce
stade. Justification : données client sensibles (CCTP, chiffrage), pas de besoin
multi-utilisateur simultané identifié au démarrage du projet. Écarté : SaaS hébergé
(complexité d'authentification et de conformité non justifiée pour un usage
mono-poste).

## 2026-06-01 — Sous-processus pour les scripts de génération (pas d'import direct)
`generer_doc.py` et `parser_dell_excel.py` sont invoqués via `subprocess.run` plutôt
qu'importés comme modules Python dans `main.py`. Justification : isolement total (une
exception ou un crash dans la génération Word n'affecte pas le process API), scripts
utilisables en ligne de commande de façon autonome pour du debug. Écarté : import direct
(plus rapide, mais couplage fort et risque de fuite d'état entre requêtes).

## 2026-06-15 — Persistance en fichiers JSON, pas de base de données
Les fiches de specs, argumentaires et documents générés sont stockés en fichiers
(JSON/Word/Excel) sur des volumes Docker montés depuis l'hôte. Justification : usage
mono-utilisateur local, pas de besoin de requêtage complexe, simplicité de sauvegarde
(copie de dossier) et de versionnement partiel (Fiches_Specs et Documents_Generes
exclus de Git par choix, voir `.gitignore`). Écarté : SQLite/Postgres (complexité non
justifiée à ce stade, migration possible plus tard si le multi-utilisateur devient
nécessaire).

## 2026-07 — Multi-moteur IA : Claude (Anthropic) et Mammouth.ai
Ajout d'un second moteur IA compatible OpenAI (Mammouth.ai, proxy vers
Mistral/DeepSeek/Sonar Pro) en alternative à Claude. Justification : dépendance à un
seul fournisseur risquée (coût, disponibilité de solde API) ; Mammouth.ai offre un accès
mutualisé moins coûteux pour un usage interne. Le choix se fait par requête
(`provider`) avec un défaut configurable par variable d'environnement
(`DEFAULT_PROVIDER`).

## 2026-07-15 — Mammouth devient le moteur par défaut (v2.3)
`DEFAULT_PROVIDER` passe de `claude` à `mammouth`. Justification : solde API Anthropic
épuisé au moment du changement (voir `docs/BLOCAGES.md`, entrée résolue). Le sélecteur
d'interface permet de repasser sur Claude à tout moment sans redéploiement.

## 2026-07 — Éditeur de schémas draw.io embarqué (v2.2)
Intégration de `jgraph/drawio:30.3.6` comme second conteneur plutôt qu'un éditeur de
schéma maison ou un service cloud (Lucidchart, diagrams.net hébergé). Justification :
image officielle open source, fonctionnement 100 % hors-ligne (variables
`DRAWIO_GOOGLE_CLIENT_ID`/`DRAWIO_MSGRAPH_CLIENT_ID` vidées), export PNG avec XML
ré-éditable embarqué directement exploitable par `python-docx`. Écarté : service SaaS
externe (fuite de données client vers un tiers, dépendance réseau).

## 2026-08-21 — Passage de pilotage Claude Code → Hermes, environnements PREPROD/PROD
Le projet, jusque-là développé en itératif sur le poste Windows de l'utilisateur (git
local + push manuel vers GitHub, historique de commits portant la trace d'un
pilotage par Claude Code — voir auteur de commit `focused-laughing-carson
<...@claude.(none)>`), passe sous pilotage Hermes avec séparation explicite
PREPROD/PROD. PREPROD = `/home/numa/projets/appel-offre` (branche `preprod`), rapatrié
via tunnel SSH depuis `C:\Projets\Appel D'offre` (poste Windows, hôte
`numa-7qy1dk3`). PROD reste à définir avec l'utilisateur (voir
`docs/BLOCAGES.md`, entrée ouverte). Écarté à ce stade : clonage direct depuis GitHub
(le HEAD distant `origin/main` était derrière la dernière modification locale
non commitée — `app/main.py` ligne 61, valeur du modèle Mammouth par défaut).
