# Journal des versions — Générateur d'appel d'offre ONE ID

## v2.7 — 2026-10-06
- **Correctif de l'identifiant de modèle GB10** : le défaut `GB10_MODEL` était `unsloth/Qwen3.8-Flash-Next-GGUF`, identifiant qui n'est plus exposé par `llm.one-id.fr/v1/models`. Sondé le 2026-10-06, il ne renvoie pas d'erreur mais laisse la requête suspendue jusqu'au timeout (90 s sans réponse à la sonde) ; le premier appel IA en PROD aurait donc été coupé par Envoy à 300 s. Nouveau défaut : `unsloth-oneid/Qwen3.8-Flash-Next-GGUF` (HTTP 200 vérifié). La variable `GB10_MODEL` est en plus posée explicitement dans le Deployment Kubernetes pour ne plus dépendre d'un défaut codé.
- `APP_VERSION` passe de 2.5 à 2.7.
- **Nouvelle étape 3 « Focus administratif »** : zone de dépôt multi-documents (RC, CCAP, AE, BPU/DPGF : PDF, DOCX, TXT), puis génération par l'IA de la *Checklist de remise*, des *Points contractuels et financiers* et des *Questions à déposer sur PLACE avant le <date lue dans les documents>*. Référence du marché et dates limites modifiables, tableaux modifiables, style des tableaux Excel (bandeau marine, en-têtes bleu-vert). Nouveaux endpoints `POST /api/admin-docs/extract` et `POST /api/recap-admin`, module `app/recap_admin.py`, section Word dans la même page paysage que le récap technique. L'assistant passe à 8 étapes.
- **Analyse administrative complète** : le budget passe de 70 000 à 240 000 caractères (réglable par `RECAP_ADMIN_MAX_CHARS`), mesure faite sur GB10. Un DCE de 5 pièces (181 k caractères) est maintenant lu en entier. L'interface affiche « Total : x / 240 000 caractères analysés ».
- **Lecture des fichiers** : support du `.xlsx`/`.xlsm` (annexes financières, BPU, DPGF : une section par feuille, valeurs calculées). Les `.docx` sont lus avec leurs tableaux, y compris pour l'analyse du CCTP. Les formats non pris en charge (`.doc`, `.xls`, autres) sont refusés avec un message clair, au lieu d'envoyer du binaire au LLM. Un document lu avec l'ancienne méthode est signalé « contenu illisible : à recharger ».
- **Nouvelle étape 2 « Récap CCTP & focus technique »** : trois tableaux générés par l'IA juste après l'analyse du CCTP, puis modifiables (cellules, ajout et suppression de lignes) : *Matrice de couverture technique*, *Plan de prise en charge recommandé*, *Ressources minimales à proposer*. Statuts : À confirmer / À préparer / À qualifier / Validé (« Validé » est réservé à l'humain). L'assistant passe à 7 étapes.
- **Nouvel endpoint** `POST /api/recap-cctp` et nouveau module `app/recap_cctp.py` (prompt optimisé Lyra + parseur tolérant).
- **Word** : nouvelle section paysage « Récapitulatif du CCTP — Focus technique » après le planning, avec les statuts non validés en rouge.
- **Fiche** : nouveau champ `affaire.recap_cctp`. Les anciennes fiches se chargent sans ce champ (tableaux vides).
- **docker-compose** : `recap_cctp.py` ajouté aux bind-mounts (le conteneur doit être recréé : `docker compose up -d`).
- **Affichage pleine largeur et responsive** : le contenu n'est plus limité à 1240 px et occupe toute la largeur de l'écran (marges qui s'adaptent à la taille de l'écran). La barre latérale « Mes fiches » se réduit à 196 px sous 1440 px de large ; le passage en une colonne sous 760 px est conservé.
- **Tableaux du récap** : les colonnes à fort contenu (Exigences principales, Attendus de preuve, Capacité ONEID, Risque, Action de réponse, et leurs équivalents dans le plan et les ressources) se partagent la largeur disponible. Les colonnes Réf., Statut et Go/No Go ont une largeur fixe de 112 px. Les cellules font au moins 150 px de haut, s'agrandissent avec le texte et gardent la même hauteur sur toute la ligne. Dans le Word, ces colonnes sont élargies (poids 1,6 contre 1,0).

## v2.5
- **Bouton ⚙ Paramètres LLM dans le header** : modale de configuration runtime du moteur IA (Base URL, Modèle en liste déroulante, Clé API), test de connexion + listing des modèles exposés par le serveur (endpoint `/v1/models` OpenAI-compatible).
- **Persistance côté serveur** : la config est stockée dans `$OUT_DIR/llm_settings.json` (mode 0600, volume Docker → survit au redémarrage du conteneur et à la mise à jour d'image). Prioritaire sur les variables d'env `GB10_*`.
- **Nouveaux endpoints** : `GET /api/settings/llm` (config masquée), `PUT /api/settings/llm` (enregistre après sonde, refuse 401), `POST /api/settings/llm/probe` (test sans persistance), `GET /api/settings/llm/models` (liste avec la clé enregistrée). Voir `docs/FONCTIONS.md`.
- **`/api/health` enrichi** : renvoie désormais `base_url` et `source` (`file` ou `env`).
- **`docker-compose.yml`** : `drawio_url.py` ajouté aux bind-mounts pour éviter l'erreur `ModuleNotFoundError` après ajout du fichier sans rebuild d'image.

## v2.3
- **Mammouth devient le moteur IA par défaut** (API OpenAI-compatible). Nouveau paramètre d'environnement `DEFAULT_PROVIDER` (`mammouth` par défaut, `claude` au choix) : c'est le moteur utilisé quand la requête n'en précise pas. Sélecteur « Moteur IA » de l'interface pré-réglé sur Mammouth.
- **Correctif appels Mammouth / Cloudflare** : les requêtes envoyaient une signature `Python-urllib`, rejetée par le Browser Integrity Check de Cloudflare (erreur 1010). Ajout d'un User-Agent navigateur validé côté cluster ; les appels passent désormais jusqu'à l'authentification.
- **Boutons IA harmonisés** : les libellés et infobulles des boutons affichent « IA » au lieu de « Claude », le moteur étant choisi dynamiquement (le sélecteur de moteur et le nom de modèle « Claude Sonnet 4.6 » restent explicites).
- **Correctif bug d'interface** : une apostrophe non échappée dans une chaîne JavaScript (« l'IA ») cassait le script et bloquait la navigation par onglets, les boutons « Suivant » et la fenêtre d'ajout de pièces jointes. Corrigé.

## v2.2
- **Nouveau template Word ONE ID** (page de garde, sommaire, en-têtes/pieds). Le générateur remplit automatiquement la page de garde : tableau *Propriétés* (Document/Version/Auteur/Date), 1re ligne de l'*Historique des évolutions*, tableau *Vos contacts* ; suppression du tableau « Informations du dossier » en doublon ; le contenu s'écrit à la suite du titre *Introduction*.
- **Saisie des contacts** dans l'assistant (Nom/Prénom/Fonction/Téléphone/E-mail), reportée dans la page de garde.
- **Éditeur de schémas draw.io intégré** (service Docker `jgraph/drawio:30.3.6`, port 8081, 100 % local) : bouton « Dessiner (draw.io) » dans la section Schéma d'architecture ; le schéma est exporté en PNG (XML ré-éditable embarqué) et inséré dans le chapitre « Architecture proposée » du Word.

## v2.1
- **Fusion Structure du dossier + Prestations** : assistant ramené à 6 étapes. La popup « Décrire l'offre » de chaque chapitre propose la liste déroulante des argumentaires, le complément d'info / options / prérequis (saisie, dictée, reformulation Claude) et le nombre de jours d'installation estimé.
- Rendu Word de chaque chapitre dans l'ordre **titre → argumentaire → complément → durée** ; génération du planning « depuis les chapitres ».
- Suppression de la « Synthèse des caractéristiques constructeur » ; la nomenclature détaillée est conservée sur toutes les parties (serveurs, stockage, switches, sauvegarde) en **police 8 pt**.
- Tableau **PRA/PCA** : colonne Paramètre 6,5 cm / Valeur 9,5 cm (pleine largeur de page).
- Argumentaire **PowerVault ME5** enrichi (contrôleurs actif-actif, iSCSI 25 GbE / FC, VAAI/SRA, RAID, CloudIQ, Veeam VSI, évolutivité).
- Nouveaux argumentaires : Access SOC, Premium SOC, Migration Exchange on-premise, Supervision, Migration AD.
- Sécurité : exclusion Git des fichiers `.env.bak*` et des sauvegardes frontend automatiques.

## v2.0
- Mode « Design » (réécriture intro/contexte/solution + thème) via API.
- Analyse CCTP + **vérification de conformité** CCTP ↔ solution (couleur de relecture).
- Onglet **Fonctionnalité** : PRA/PCA (RTO/RPO, cible, méthode) avec argumentaires par cas éditables.
- Module **Sauvegarde** : volumétrie multi-sites (Total auto), cas Veeam/PPDM × baie SAN / PowerProtect Data Domain, option réplication Cloud ONE ID.
- Chapitre auto **Sauvegarde PowerStore + PowerProtect** (déclenché par la configuration).
- Onglet **Kanban** : regroupement des points d'attention en chapitres (proposition auto via IA), description par chapitre (saisie/dictée/reformulation + images), génération dans l'ordre.
- **Chapitres administratifs** figés ajoutés en fin de document (fusion docx, images conservées).
- **Multi-moteur IA** : choix Claude (Anthropic) ou Mammouth (Mistral, DeepSeek, Sonar Pro…).
- Dictée vocale, police Assistant 11 + gras auto des termes clés, sauts de page entre chapitres.
- Numéro de version + build daté automatique ; préambule qualité ONE ID appliqué à tous les appels IA.

## v1.0
- Version initiale : formulaire Serveurs/Stockage/Switches/Sauvegarde, import Excel Dell,
  génération Word ONE ID, argumentaires produits sourcés, planning/Gantt, bibliothèque de fiches, déploiement Docker.
