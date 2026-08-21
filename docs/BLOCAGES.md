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
