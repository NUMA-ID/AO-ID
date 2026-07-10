# Journal des versions — Générateur d'appel d'offre ONE ID

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
