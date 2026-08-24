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

## 2026-08-21 — `.gitattributes` : normalisation LF pour le code, binaire protégé pour les documents
Ajout d'un `.gitattributes` fixant `eol=lf` pour tous les fichiers texte (py, html, js,
css, json, md, yml, txt, Dockerfile) et `binary` explicite pour les formats Office/image
(docx, dotx, xlsx, png, jpg, pdf, pptx, zip). Justification : le poste Windows source
enregistre en CRLF, ce qui produisait des diffs de plusieurs milliers de lignes sans
changement de contenu réel à chaque synchronisation (observé dans le commit `5a18b30` du
2026-08-21). Écarté : laisser `core.autocrlf` géré uniquement côté client (fragile,
dépend de la configuration de chaque poste qui clone/synchronise le dépôt) ; normaliser
aussi les binaires (aurait corrompu les .docx/.xlsx — `text=auto` ne s'applique jamais
aux fichiers marqués `binary`).

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

## 2026-08-21 — Développement et exécution exclusivement sur la machine Linux Hermes
Décision de l'utilisateur : ne plus jamais démarrer, builder ou modifier le projet
directement sur le poste Windows. Tout le cycle (édition, `docker compose up`, tests,
commits) se fait désormais sur la machine Linux Hermes (`djinn-bot`) où tourne le
présent agent. Justification : élimine à la source la classe de problèmes rencontrée le
même jour (drift CRLF/Windows vs dépôt Git, working tree local en avance sur
`origin/main` sans traçabilité, poste Windows non contrôlé par le pilotage Hermes).
Vérifié opérationnel le jour même : build Docker complet exécuté sur `djinn-bot`,
conteneurs `ao-oneid` et `ao-drawio` démarrés, `/api/health` répond `ok:true`. Écarté :
garder un développement mixte Windows/Linux (aurait reproduit le problème que ce
changement vise justement à éliminer). Le poste Windows n'est plus qu'un point
d'origine historique ; il n'est plus une cible de déploiement ni un environnement de
travail.

## 2026-08-23 — Ajout d'un troisième moteur IA : Mistral AI direct
Ajout de Mistral AI en accès direct (API officielle `api.mistral.ai`), en plus de
Claude (Anthropic) et Mammouth.ai (qui proxifie déjà Mistral parmi d'autres modèles).
Justification : demande explicite de l'utilisateur d'avoir un accès direct au fournisseur
Mistral avec sa propre clé, indépendamment du proxy Mammouth (autre compte, autre
facturation, autre disponibilité). Implémentation symétrique à Mammouth
(`llm_complete()`, branche `provider == "mistral"`, appel `urllib` OpenAI-compatible vers
`/chat/completions`, modèle par défaut `mistral-medium-latest`). Sélecteur d'interface
étendu avec un troisième choix "Mistral (direct)" et sa propre liste de modèles
(Medium/Large/Small). Testé en conditions réelles le jour même via
`POST /api/ameliorer-solution` avec `provider=mistral` : réponse cohérente obtenue.
Écarté : fusionner cette entrée avec le moteur Mammouth existant (les deux comptes/clés
sont distincts et doivent pouvoir être activés indépendamment).
