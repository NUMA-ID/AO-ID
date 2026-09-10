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

## 2026-08-24 — Appels IA délégués au threadpool (run_in_threadpool)
Cause racine identifiée d'un redémarrage de pod signalé en PROD (v2.4.1, voir
`appel-offre-k8s/docs/BLOCAGES.md`) : `llm_complete()` et `design_enhance()` sont des
fonctions synchrones (`urllib.request.urlopen`, timeout 180s) appelées directement
depuis des routes `async def` de FastAPI. Avec Uvicorn en un seul worker, un appel IA
en cours bloquait entièrement la boucle d'événements asyncio, y compris les requêtes
`GET /` utilisées par les probes Kubernetes — d'où un faux-positif de la liveness probe
et un redémarrage du pod en pleine réponse à un utilisateur. Correctif : les 6 points
d'appel (`analyse-cctp`, `proposer-chapitres`, `verifier`, `ameliorer-solution`,
`memoire`, `generer` en mode design) passent par `starlette.concurrency.run_in_threadpool`
plutôt que d'appeler la fonction bloquante directement. Aucune nouvelle dépendance
(`starlette` fourni par `fastapi==0.115.6`). Testé en conditions réelles (PREPROD) :
`GET /` répond en 5ms pendant qu'un appel IA est en cours de traitement, alors qu'avant
ce correctif la requête aurait été bloquée jusqu'à la fin de l'appel. Écarté : réécrire
`llm_complete()` en natif asynchrone (`httpx.AsyncClient`) — plus invasif pour un gain
équivalent dans le contexte actuel (un seul worker, faible concurrence attendue) ;
pourra être reconsidéré si le nombre d'utilisateurs simultanés augmente.

## 2026-08-24 — Quatrième moteur IA : GB10 (serveur vLLM interne ONE ID)
Ajout d'un moteur GB10, pointant vers `https://llm.one-id.fr/v1` (serveur vLLM interne
ONE ID, machine GB10/DGX Spark administrée par l'équipe infra — Thibaud Melano, voir
tickets CRM `TT038490`). Justification : accès à un modèle auto-hébergé (Qwen3.8 via
Unsloth, `unsloth/Qwen3.8-Flash-Next-GGUF`), sans dépendance à un fournisseur externe ni
coût par requête, utile en secours quand Claude/Mammouth/Mistral sont indisponibles ou
rate-limited (cas vécu le jour même avec Mistral, HTTP 429). Implémentation symétrique
aux moteurs OpenAI-compatibles existants (`llm_complete()`, branche `provider == "gb10"`,
`GB10_API_KEY`/`GB10_BASE` en variables d'environnement). Particularité gérée : ce modèle
est de type "reasoning" et renvoie un champ `reasoning_content` séparé du `content` final
dans la réponse API — seul `content` est retourné à l'appelant. Sélecteur d'interface
étendu avec un quatrième choix "GB10 (interne ONE ID)". Testé en conditions réelles :
appel direct à l'API (34,5s pour un prompt simple) et via `/api/analyse-cctp`
(138,8s, `HTTP 200`, JSON valide) — le modèle est sensiblement plus lent que Mistral/
Claude du fait de son raisonnement interne, mais reste sous le timeout de 180s de
`llm_complete()`. Écarté à ce stade : réduire le timeout spécifiquement pour ce
provider (aucune limite basse n'a été demandée) ; exposer le `reasoning_content` dans
l'interface (non demandé, alourdirait l'affichage).

## 2026-09-09 — GB10 devient le seul moteur IA (retrait de Claude, Mammouth, Mistral)
Décision utilisateur : ne conserver que le moteur GB10 (serveur vLLM interne ONE ID) et
retirer complètement les trois autres (Claude/Anthropic, Mammouth.ai, Mistral direct).
Justification : le serveur GB10 est auto-hébergé, sans coût par requête ni dépendance à un
fournisseur externe, et sans les limites de débit rencontrées (Mistral HTTP 429). Portée du
retrait (choix « suppression complète et propre ») : branches backend Claude/Mammouth/Mistral
supprimées de `llm_complete()` (ne reste que GB10) ; variables `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL`/
`MAMMOUTH_*`/`MISTRAL_*` retirées du code, de `.env.example`, du `Dockerfile` et des notes K8s ;
options du sélecteur d'interface retirées. Le **sélecteur « Moteur IA » est conservé** avec GB10
comme unique option (choix utilisateur : réintroduction facile d'un futur moteur). `DEFAULT_PROVIDER`
passe de `mammouth` à `gb10`. Testé en conditions réelles (PREPROD) : health OK, `/api/analyse-cctp`
sans provider explicite → `HTTP 200`, JSON complet et cohérent généré par GB10. Écarté : retirer
entièrement le sélecteur (rendrait la réintroduction d'un moteur plus lourde) ; conserver les clés
en réserve (l'utilisateur a explicitement demandé une suppression complète). Réversibilité : le code
des anciens moteurs reste récupérable via l'historique Git (tags `v2.4.x`).

## 2026-09-09 — Bibliothèques de shapes ONE ID chargées automatiquement dans draw.io
Les shapes ONE ID (convertis depuis les stencils Visio de `C:\Projets\Formes`, 124 bibliothèques /
~6 220 shapes, rangés par constructeur : Dell, Fortinet, VMware, HPE, Aruba, Cisco, EMC, NetApp,
Nutanix, Palo Alto, Sophos, Stormshield, Brocade, Datacore, Microsoft, + Autres/Raritan) sont
désormais **versionnés dans le dépôt** (`app/web/drawio-libs/*.xml`, format `mxlibrary`, 187 Mo
au total, fichiers consolidés `_PAR_CONSTRUCTEUR`) et **chargés automatiquement** à l'ouverture de
l'éditeur. Justification : ces librairies ne vivaient que dans le localStorage du navigateur (par
origine) — fragiles, perdues au moindre vidage de cache ou changement d'adresse d'accès (cause de
leur « disparition » signalée le 09/09). Mécanisme retenu : paramètre d'URL natif draw.io
`&clibs=U<url_encodée>` (une URL par bibliothèque, séparées par `;`), les fichiers étant servis par
deux nouvelles routes de l'app (`GET /api/drawio-libs` = liste, `GET /drawio-libs/<nom>` = contenu,
avec en-tête CORS `Access-Control-Allow-Origin: *` car draw.io tourne sur le port 8081 et fetch
depuis le port 8080). Écarté : (1) l'action embed `load-libraries` par postMessage — **non supportée**
par draw.io 30.3.6 (vérifié dans le JS du conteneur, l'action n'existe pas) ; (2) laisser les shapes
en localStorage (fragile, cause du problème) ; (3) n'auto-charger qu'un sous-ensemble de marques —
l'utilisateur a explicitement choisi de charger les 16 bibliothèques.
⚠️ **Limite de performance connue et non résolue** : charger 187 Mo de PNG base64 au démarrage
(dont DELL 47 Mo, VMware 35 Mo, FORTINET 19 Mo) alourdit l'éditeur au premier affichage — le service
serveur est rapide (0,13 s pour 47 Mo en local) mais le décodage base64→images côté navigateur peut
ramer, d'autant plus via le tunnel SSH. Non mesuré côté navigateur (le preview Hermes ne rend pas
l'iframe draw.io). Si l'ouverture est trop lente à l'usage, réduire à un sous-ensemble de marques
(retirer des fichiers de `app/web/drawio-libs/` — la liste est dynamique, aucune autre modif requise).

## 2026-09-09 — Watchdog de tunnel SSH pour l'accès distant à PREPROD
Le tunnel SSH inversé vers le poste Windows (`ssh -R 8080:localhost:8080 -R
8081:localhost:8081`, utilisé pour exposer AO-ID/draw.io au navigateur de
l'utilisateur) tombait de façon répétée et nécessitait une relance manuelle à
chaque fois. Script `tunnel-watchdog.sh` ajouté à la racine du dépôt : boucle
`while true` relançant le tunnel automatiquement (nouvelle tentative après 5s)
en cas de coupure, avec keepalive SSH renforcé (`ServerAliveInterval=15`,
`ServerAliveCountMax=6`, `TCPKeepAlive=yes`) et journal horodaté
(`tunnel-watchdog.log`, non versionné). Écarté : solution plus lourde (service
systemd, VPN) — non nécessaire tant que l'usage reste ponctuel côté
utilisateur ; à reconsidérer si le besoin devient permanent. Limite connue :
le watchdog tourne tant que la session `djinn-bot` reste active, ne survit pas
à un redémarrage de la machine.

## 2026-09-09 — Nouvel argumentaire Cisco Nexus 3172TQ
Ajout d'un argumentaire pour le commutateur Data Center **Cisco Nexus 3172TQ**
(N3K-C3172TQ-10GT, 48 ports 10GBASE-T + 6 QSFP+), à la demande explicite de
l'utilisateur. Données techniques sourcées depuis la fiche technique Cisco
officielle (`data_sheet_c78-729483`) — aucune caractéristique inventée. Image
produit récupérée depuis une fiche revendeur tierce (ITinStock, photo façade
avant), **vérifiée visuellement** avant intégration (étiquette "CISCO NEXUS
3172TQ" lisible sur la photo, configuration de ports conforme). Point
d'attention explicitement documenté dans l'argumentaire lui-même : ce modèle
est en fin de commercialisation chez Cisco (End of Sale ; support jusqu'au
28/02/2027) — signalé à l'utilisateur final du document plutôt que dissimulé.
Testé en conditions réelles : JSON validé, argumentaire détecté par
`/api/argumentaires` (33 argumentaires au total après ajout).
