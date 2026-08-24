# Générateur d'appel d'offre ONE ID

Application locale (Docker) qui assiste la rédaction des dossiers d'appel d'offre infrastructure ONE ID : analyse du CCTP, import des configurations Dell, structuration du dossier, planning, génération du mémoire technique Word, chiffrage Excel et remplissage du cadre de mémoire technique — le tout piloté par un assistant en 7 étapes.

---

## Prérequis

- **Docker Desktop** (Windows/Mac/Linux).
- Une **clé API** pour les fonctions IA :
  - **Anthropic (Claude)** — https://console.anthropic.com → API Keys, et/ou
  - **Mammouth.ai** (optionnel, moteur alternatif : Mistral, DeepSeek, Sonar…) — https://mammouth.ai/app/account/settings/api

Les fonctions IA (analyse CCTP, reformulation, vérification de conformité, proposition de chapitres, remplissage du cadre) nécessitent une clé. Le reste de l'application (saisie, génération Word/Excel, planning) fonctionne sans clé.

---

## Configuration

1. Copier le modèle d'environnement :
   ```
   cd app
   copy .env.example .env        (Windows)   |   cp .env.example .env   (Mac/Linux)
   ```
2. Renseigner `app/.env` :
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ANTHROPIC_MODEL=claude-sonnet-4-6
   MAMMOUTH_API_KEY=            # optionnel
   MAMMOUTH_BASE=https://api.mammouth.ai/v1
   ```
   > Le fichier `.env` n'est **jamais** versionné (protégé par `.gitignore`).

---

## Démarrage

```
cd app
docker compose up -d --build
```

Puis ouvrir : **http://localhost:8080**

- Après une simple modification de code, `docker compose up -d` suffit (rechargement auto activé).
- Un `--build` n'est nécessaire qu'en cas de changement de dépendances.

Arrêt : `docker compose down`.

---

## Utilisation — l'assistant en 7 étapes

1. **CCTP & contexte** — déposer le CCTP (PDF/Word/TXT) ; l'IA en extrait le contexte et les points d'attention.
2. **Équipements** — importer l'export Excel Dell (Solutions Configurator) et compléter à la main (firewall, switch, wifi…).
3. **Fonctionnalité** — PRA/PCA (RTO/RPO, cible, méthode) et sauvegarde (Veeam/PPDM, baie SAN / Data Domain, réplication Cloud), avec argumentaires par cas.
4. **Structure du dossier (Kanban)** — regrouper les points d'attention en chapitres (proposition automatique par l'IA), décrire chaque chapitre (saisie/dictée/reformulation + images).
5. **Prestations & méthodologie** — intitulé, durée et méthodologie par prestation.
6. **Planning** — diagramme de Gantt (dérivable des prestations) ; couleurs par type (tâche / réception matériel / télétravail / congé).
7. **Documents & historique** — générer le **mémoire technique Word**, le **chiffrage Excel**, remplir le **cadre de mémoire technique** du client (IA), **vérifier la conformité** au CCTP, puis **enregistrer le dossier** dans l'historique.

Le choix du **moteur IA** (Claude ou Mammouth) se fait dans la barre du bas et s'applique à tous les boutons IA.

---

## Structure des dossiers

```
Appel D'offre/
├─ app/
│  ├─ main.py               API FastAPI (endpoints IA, génération, chiffrage, mémoire)
│  ├─ web/index.html        interface (assistant 7 étapes)
│  ├─ engine/               moteur de génération Word (python-docx) + parseur Excel Dell
│  ├─ assets/               modèle Word ONE ID + CHAPITRES_ADMIN.docx (chapitres figés)
│  ├─ requirements.txt · Dockerfile · docker-compose.yml · .env
├─ Documentation_Constructeur/   argumentaires éditables (JSON) : produits, PRA/PCA, sauvegarde…
├─ Fiches_Specs/            dossiers enregistrés (historique)   — non versionné
├─ Documents_Generes/       Word / Excel / mémoires produits    — non versionné
├─ CHANGELOG.md · README.md · .gitignore
```

### Argumentaires éditables

Le dossier `Documentation_Constructeur/<PRODUIT>/argumentaire.json` pilote les textes commerciaux insérés dans le Word (produits Dell, cas PRA/PCA, cas sauvegarde Veeam/PPDM × SAN/Data Domain, chapitre combiné PowerStore + PowerProtect). Ils sont relus à chaque génération : les modifier ne demande aucun redéploiement.

---

## Versionnement (Git)

- Le numéro de **version** (`v2.0`) s'affiche dans l'interface ; le **build** (date) est calculé automatiquement.
- À chaque jalon :
  ```
  git add .
  git commit -m "vX.Y — description"
  git tag vX.Y
  git push --follow-tags
  ```
- Historique des versions : voir `CHANGELOG.md`.

---

## Règles et limites

- **Véracité** : les fonctions IA appliquent un cadre strict (« ne rien inventer ») ; toute donnée non vérifiable est laissée « à préciser ». Les valeurs constructeur (ex. taux de recyclage) ne sont pas inventées.
- **Cadre de mémoire technique** : il est régénéré selon la structure de la trame client (la mise en forme exacte du fichier d'origine n'est pas conservée). Format **`.doc` non pris en charge** → enregistrer en `.docx`.
- **Police** : le Word utilise la police **Assistant** ; l'installer sur le poste qui ouvre le document pour un rendu fidèle.
- Les documents générés et les fiches contiennent des données client : ils sont **exclus du dépôt Git** par défaut.

---

## Documentation complémentaire

- `docs/ARCHITECTURE.md` — composants, flux de données, dépendances externes.
- `docs/FONCTIONS.md` — inventaire exhaustif des endpoints (entrées/sorties/erreurs/effets de bord).
- `docs/DECISIONS.md` — choix techniques structurants et leur justification.
- `docs/BLOCAGES.md` — journal des points bloquants (ouvert/contourné/résolu).
- `docs/EXPLOITATION.md` — variables d'environnement, secrets, procédure de déploiement/retour arrière.

## Pilotage du projet (Hermes)

Depuis le 2026-08-21, ce projet est piloté via Hermes selon un modèle **PREPROD /
PROD** : tout le travail se fait en PREPROD (`/home/numa/projets/appel-offre`, branche
`preprod`) et rien n'est déployé en PROD sans validation explicite. L'environnement
PROD n'est pas encore défini (voir `docs/BLOCAGES.md`). Avant cette date, le projet
était développé en itératif directement sur le poste Windows de l'utilisateur, avec des
commits poussés manuellement vers `github.com/NUMA-ID/AO-ID` (branche `main`).
