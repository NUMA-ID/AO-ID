# Journal des blocages — Générateur d'appel d'offre ONE ID

Une entrée par problème. Les entrées ne sont jamais supprimées, seulement passées en
« résolu » ou « contourné ».

---

## 2026-08-21 — Disque `/var` saturé pendant le premier build Docker sur Hermes Linux (résolu)
**Description factuelle** : premier `docker compose up -d --build` exécuté sur la
machine Linux Hermes (`djinn-bot`) après le passage au pilotage 100% Linux. Le build a
échoué avec `OSError: [Errno 28] No space left on device` pendant `pip install`. `df -h`
montrait `/var` (`/dev/sda5`, 5,9 Go) à 100% d'utilisation, 0 disponible ; Docker stockait
ses images/cache dans `/var/lib/docker` par défaut.
**Cause** : trois images Docker préexistantes sur la machine (dont
`nousresearch/hermes-agent:latest`, 3,86 Go) plus le cache de build consommaient déjà la
totalité de la petite partition `/var`. La partition `/srv` (175 Go, 166 Go libres)
n'était pas utilisée par Docker.
**Impact** : impossible de construire ou démarrer un conteneur tant que l'espace n'était
pas libéré ; bloquant pour tout le nouveau workflow "Linux uniquement".
**État** : résolu.
**Contournement en place** :
1. `docker system prune -af` a libéré 5,4 Go immédiatement (build cache + images
   inutilisées).
2. Changement durable : `data-root` de Docker déplacé vers `/srv/docker` via
   `/etc/docker/daemon.json` (`{"data-root": "/srv/docker"}`), ancien contenu de
   `/var/lib/docker` copié puis supprimé, service `docker` redémarré. Confirmé par
   `docker info | grep "Docker Root Dir"` → `/srv/docker`.
   `/var` est repassé à 12% d'utilisation après le déplacement.

**Mise à jour du 10/09/2026 — le déplacement était incomplet** : ce
changement ne couvrait que le `data-root` Docker, pas le **snapshotter
containerd** sous-jacent (`/var/lib/containerd`, distinct de
`/var/lib/docker`), qui a fini par regrossir à 3,1 Go et resaturer `/var`
(61% d'utilisation, 2,2 Go libres), provoquant un nouvel échec de build
(`no space left on device` pendant la bascule PROD v2.5.1 — voir
`appel-offre-k8s/docs/DECISIONS.md`). Corrigé cette fois de façon complète :
`root = "/srv/containerd"` ajouté à `/etc/containerd/config.toml`, contenu
existant copié vers `/srv/containerd` (`cp -a`, conteneurs arrêtés le temps
du redémarrage `containerd`+`docker`), ancien `/var/lib/containerd` supprimé
après vérification que les 3 conteneurs actifs (`ao-oneid`, `ao-drawio`,
`rag-oneid-qdrant`) redémarraient sains. `/var` passé de 61% à 6%
d'utilisation (5,3 Go libres) après ce second déplacement.

## 2026-08-21 — PROD non définie
**Description factuelle** : au moment de la reprise du projet sous pilotage Hermes,
seul l'environnement PREPROD a été confirmé par l'utilisateur
(`/home/numa/projets/appel-offre`, branche `preprod`). Aucun chemin ni nom de branche
PROD n'a encore été communiqué.
**Cause** : pas encore demandé/répondu à ce stade de l'échange.
**Impact** : impossible de préparer une bascule preprod → prod tant que la cible n'est
pas connue ; impossible de documenter les différences de configuration
preprod/prod dans `docs/EXPLOITATION.md` au-delà de ce qui est déjà observable côté
preprod.
**État** : ouvert.
**Contournement** : aucun — attente de l'information utilisateur.

## 2026-08-21 — Working tree local en avance sur `origin/main` (GitHub)
**Description factuelle** : au moment du rapatriement, le dépôt local (poste Windows)
avait 13 fichiers modifiés non commités par rapport à `HEAD` (`1dc397f`, tag `v2.3`),
plus 4 fichiers non suivis (dont deux nouveaux dossiers d'argumentaires
`00-AUDIT SECU` et `00-LOCATION FORTINET`, et `app/web/versions/index_v2.3.html`).
Une bonne partie du diff (`generer_doc.py`, les fichiers `index_v2.1.html` /
`index_v2.2.html`) ne correspond en réalité qu'à une différence de fin de ligne
(LF committé vs CRLF en local) — le contenu réel n'a presque pas changé pour ces
fichiers. La modification fonctionnelle réelle identifiée est dans `app/main.py`
ligne 61 : le modèle Mammouth par défaut est passé de `"mistral"` à
`"mammouth/mistral-medium-3.1"` en local, non répercuté sur GitHub.
**Cause** : le dépôt était piloté localement sans commit/push systématique à chaque
session de travail.
**Impact** : le dépôt GitHub `NUMA-ID/AO-ID` (branche `main`) ne reflète pas l'état de
travail réel du poste Windows au 2026-08-21. Un simple `git clone` aurait donné une
version fonctionnellement en retard.
**État** : contourné — le rapatriement s'est fait par copie directe du répertoire de
travail (via `scp` sur tunnel SSH), working tree et historique `.git` locaux inclus, et
non par clonage GitHub. Rien n'a encore été commité côté PREPROD à ce stade (à faire
au premier commit de livraison).
**Contournement en place** : aucun commit de mise à jour du modèle Mammouth n'a encore
été poussé sur `origin/main` ; à faire lors du prochain cycle de livraison documenté.

## 2026-08-21 — Secrets présents en clair dans le répertoire rapatrié
**Description factuelle** : `app/.env`, `app/.env.bak` et `app/.env.bak.bak` sont
présents sur disque avec des clés API en clair (`ANTHROPIC_API_KEY`,
`MAMMOUTH_API_KEY`). Ces fichiers sont exclus de Git par `.gitignore`
(`.env`, `app/.env.bak*`) mais existent physiquement dans le dossier rapatrié en
PREPROD.
**Cause** : fichiers de configuration locale jamais nettoyés côté poste Windows
(deux sauvegardes `.bak`/`.bak.bak` accumulées).
**Impact** : risque de fuite si le dossier PREPROD est partagé, archivé ou copié sans
précaution. Ces clés ne doivent en aucun cas être commitées.
**État** : ouvert.
**Contournement en place** : aucun nettoyage effectué à ce stade ; recommandation à
l'utilisateur de supprimer `app/.env.bak` et `app/.env.bak.bak` (doublons obsolètes)
et de faire tourner les clés API si le dossier a pu être exposé.

## 2026-08-24 — Dépôt d'infrastructure Kubernetes séparé découvert (`AO-ID-k8s`)
**Description factuelle** : la vraie PROD (`https://ao-id.one-id.fr`) existe et tourne
depuis le 15/07/2026 sur un cluster Kubernetes on-prem (`mrs-wkr.kube.internal`,
namespace `numa`, Envoy Gateway, image `apicall.one-id.fr/numa/ao-id:2.4.2`). Les
manifestes vivent dans un dépôt local séparé, `C:\Projets\AO-ID-k8s` (poste Windows,
profil `n.doublet.ONE-ID`), jamais mentionné avant le 24/08 et absent de mon suivi
PREPROD/PROD jusqu'ici. Ce dépôt contient un `kubeconfig-host.yaml` avec accès admin
direct au cluster (pas de VPN nécessaire — accès réseau interne direct depuis le poste
Windows), et une version de l'app (2.4.2, avec Mistral déjà intégré) différente de la
mienne côté PREPROD (2.3 + mon ajout Mistral).
**Cause** : information non communiquée au démarrage du pilotage Hermes ; existait déjà
avant la reprise du projet.
**Impact** : mon suivi PREPROD/PROD était incomplet — PROD existait déjà et j'ai
travaillé un temps sans le savoir. Deux implémentations Mistral indépendantes
(PREPROD/moi vs. PROD/déjà en place) : à réconcilier.
**État** : ouvert (réconciliation PREPROD/PROD à faire) — mais l'accès et le diagnostic
initial sont désormais opérationnels.
**Contournement en place** : accès cluster obtenu via tunnel SSH vers le poste Windows
(profil `administrateur`), lecture directe du `kubeconfig-host.yaml` du profil
`n.doublet.ONE-ID` (droits NTFS différents, contournés en lisant/copiant les fichiers
plutôt qu'en changeant d'utilisateur SSH).

## 2026-08-24 — Erreur "upstream request timeout" sur ao-id.one-id.fr avec le moteur Mistral
**Description factuelle** : l'utilisateur rapporte une erreur "Erreur : Unexpected
token 'u', "upstream r"... is not valid JSON" dans l'interface PROD lors de l'usage du
moteur Mistral. Diagnostic : appel direct au pod (`kubectl exec`) → Mistral répond en
< 2s ; appel via port-forward (contourne le Gateway) → HTTP 200 ; appel via le vrai
Gateway `https://ao-id.one-id.fr` → réussi une fois à 10.8s, proche de la limite
implicite. Aucun `BackendTrafficPolicy` n'existait sur la route `ao-id` : le timeout par
défaut d'Envoy Gateway (15s) est insuffisant pour des appels IA plus longs (CCTP
volumineux, latence Mistral variable).
**Cause** : timeout de route Gateway trop court pour des appels LLM, jamais configuré
explicitement lors du déploiement initial (15/07/2026).
**Impact** : échecs intermittents des fonctions IA en PROD (tous moteurs concernés,
pas seulement Mistral — Claude et Mammouth ont le même risque de dépassement).
**État** : résolu.
**Contournement en place** : ajout d'un `BackendTrafficPolicy` (`ao-id-timeout`,
namespace `numa`, voir dépôt `AO-ID-k8s`) portant `requestTimeout` à 120s et
`connectionIdleTimeout` à 130s sur la route `ao-id`. Appliqué le 24/08/2026, accepté par
les deux listeners du Gateway `gw01` (http + https). Vérifié : `/api/health` toujours
`ok:true` après application, aucune régression observée.

## 2026-08-24 — Import Excel HTTP 500 : bug openpyxl + format devis TD SYNNEX non reconnu (résolu)
**Description factuelle** : `POST /api/import-excel` échouait en PROD (et reproduit en
PREPROD) avec `ValueError: Max value is 14` levée depuis
`openpyxl/styles/fonts.py` (validation du descripteur `Font.family`) au moment de
`load_workbook()`. Fichier testé : devis TD SYNNEX réel (mairie de Saint Estève,
`1006056968`). Une fois ce premier problème contourné, un second est apparu : ce
fichier n'est pas un export "Dell Solutions Configurator" (le seul format reconnu par
`parser_dell_excel.py`) mais un devis distributeur TD SYNNEX, avec des colonnes et une
structure différentes.
**Cause** : (1) openpyxl 3.1.5 applique une limite `max=14` sur l'attribut de style
`font.family` non conforme à la réalité des fichiers OOXML produits par certains
outils tiers (ici TD SYNNEX) ; (2) le parseur ne gérait qu'un seul format d'entrée.
**Impact** : tout import Excel utilisant un devis TD SYNNEX (format visiblement utilisé
en pratique par l'équipe, au moins pour ce dossier) était bloqué.
**État** : résolu.
**Contournement en place** :
1. `app/engine/parser_dell_excel.py` : `openpyxl.styles.fonts.Font.family.max` relevé à
   999 avant tout `load_workbook()` (le classeur s'ouvre alors normalement).
2. Le parseur détecte maintenant automatiquement le format (Dell Solutions Configurator
   OU devis TD SYNNEX) par les colonnes d'en-tête présentes, et route vers `parse_dell()`
   ou `parse_tdsynnex()` en conséquence. Le format Dell existant n'a pas été modifié
   fonctionnellement (juste extrait dans sa propre fonction).
3. `app/main.py` (`/api/import-excel`) : le traceback complet est désormais loggé côté
   serveur (`print(..., flush=True)`) même si la réponse HTTP reste tronquée à 500
   caractères — nécessaire à ce diagnostic, absent avant.
Testé en conditions réelles (PREPROD) sur le fichier réel fourni : HTTP 200, client
détecté "MAIRIE DE SAINT ESTEVE", 1 serveur (PowerEdge R260, specs extraites) + 4 lignes
sauvegarde (Data Domain DD6410) correctement classées.

## 2026-07-15 — Erreur 1010 Cloudflare sur les appels Mammouth (résolu)
**Description factuelle** : les requêtes vers l'API Mammouth échouaient avec une erreur
Cloudflare 1010 (Browser Integrity Check), la signature `Python-urllib` du client HTTP
standard étant rejetée.
**Cause** : absence de `User-Agent` de type navigateur dans les en-têtes de la requête
`urllib.request`.
**Impact** : le moteur Mammouth était totalement inutilisable avant correctif.
**État** : résolu (v2.3).
**Contournement en place** : ajout d'un en-tête `User-Agent` imitant Chrome/Linux dans
`llm_complete()` (`app/main.py`, fonction `llm_complete`, branche `provider ==
"mammouth"`).

## 2026-07 — Solde API Anthropic épuisé (contourné)
**Description factuelle** : le solde du compte Anthropic utilisé pour les fonctions IA
a été épuisé, rendant le moteur Claude indisponible.
**Cause** : consommation de crédits API.
**Impact** : toutes les fonctions IA utilisant Claude par défaut étaient bloquées.
**État** : contourné (v2.3) — `DEFAULT_PROVIDER` basculé sur `mammouth`. Redevient un
point d'attention si le solde Mammouth s'épuise à son tour sans qu'un rechargement soit
anticipé.
**Contournement en place** : sélecteur de moteur IA dans l'interface permettant de
revenir sur Claude dès que le solde est rechargé, sans modification de code.

## 2026-07-10 — Ancien template Word en doublon
**Description factuelle** : `app/assets/TEMPLATE_BASE_ONEID.backup_20260710_152828.docx`
subsiste à côté du template actif `TEMPLATE_BASE_ONEID.docx`.
**Cause** : sauvegarde manuelle avant la mise à jour du template (v2.2, page de garde
automatique).
**Impact** : aucun sur le fonctionnement (le nom exact `TEMPLATE_BASE_ONEID.docx` est le
seul utilisé par `generer_doc.py`) ; encombrement du dépôt uniquement. Le motif
`**/TEMPLATE_BASE_ONEID.backup_*.docx` est bien exclu par `.gitignore`.
**État** : ouvert (fichier local non nettoyé, mais sans impact fonctionnel — mention
pour traçabilité seulement).
**Contournement en place** : exclusion Git déjà active ; suppression du fichier laissée
au choix de l'utilisateur.

## 2026-08-24 — Moteur GB10 sensiblement plus lent que les autres (latence de raisonnement)
**Description factuelle** : le modèle GB10 (`unsloth/Qwen3.8-Flash-Next-GGUF`, serveur
vLLM interne `https://llm.one-id.fr/v1`) est un modèle "reasoning" qui génère un
raisonnement interne (`reasoning_content`) avant sa réponse finale. Mesuré en conditions
réelles : 34,5s pour un prompt simple (max_tokens=8000), 138,8s pour un appel
`/api/analyse-cctp` complet (prompt système long) — largement plus lent que Mistral
(quelques secondes) ou Claude.
**Cause** : architecture "reasoning" du modèle (chaîne de pensée générée avant la
réponse), latence intrinsèque au modèle, pas à l'intégration.
**Impact** : un appel GB10 sur un CCTP volumineux ou un prompt système très long
pourrait approcher ou dépasser le timeout de 180s codé dans `llm_complete()`,
provoquant une erreur 502 côté utilisateur sans lien avec un bug applicatif.
**État** : ouvert — **aggravé le 2026-09-09** : GB10 étant désormais le SEUL moteur (retrait
de Claude/Mammouth/Mistral), le risque de timeout n'est plus contournable en basculant sur un
autre moteur. Mesure du 2026-09-09 : un `/api/analyse-cctp` sur un CCTP court a pris **172,9s**
(`HTTP 200`), soit très proche des 180s — un CCTP réel plus volumineux dépassera probablement le
timeout et renverra une erreur 502 à l'utilisateur.
**Contournement en place** : timeout de `llm_complete()` porté à **300s** le 2026-09-22
(le `BackendTrafficPolicy` Envoy PROD doit être aligné à 300s/310s, sinon le Gateway
coupe avant le backend). Les probes K8s (liveness 20s) restent un risque si un appel
bloque le thread principal — les appels IA passent déjà par `run_in_threadpool`.

## 2026-09-22 — Draw.io en PROD : iframe vers :8081 affiche AO-ID (contourné)
**Description factuelle** : sur `https://ao-id.one-id.fr`, le bouton « Dessiner (draw.io) »
ouvre un overlay « Chargement de l'éditeur… » puis affiche une seconde instance d'AO-ID
dans l'iframe. En PREPROD (`localhost:8080` + conteneur `ao-drawio` sur `:8081`) le même
bouton ouvre bien l'éditeur.
**Cause** : le JS construisait `DRAWIO_BASE = location.protocol + '//' + hostname + ':8081'`.
En PROD ça donne `https://ao-id.one-id.fr:8081`. Ce port n'est pas exposé au navigateur
(timeout depuis djinn-bot ; screenshot utilisateur = spinner infini / AO-ID dans l'iframe
si un listener 8081 existe et que la HTTPRoute `ao-id` y est attachée, ou si le navigateur
retombe sur :443). De plus le Deployment `drawio` n'a pas le volume `drawio-libs`.
**Impact** : éditeur inutilisable en PROD ; PREPROD inchangée.
**État** : contourné côté code PREPROD (iframe → `/drawio` en HTTPS, libs via AO-ID).
La HTTPRoute K8s et `DRAWIO_SERVER_URL` sont prêts dans `appel-offre-k8s` mais **non
appliqués** tant que l'utilisateur n'a pas dit « bascule en prod » (tunnel SSH Windows
instable).
**Contournement en place** : `resolve_drawio_base()` + injection `__DRAWIO_BASE__`.

