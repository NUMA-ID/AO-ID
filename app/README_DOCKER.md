# Application Appel d'offre ONE ID — Docker Desktop

Application web complète (backend Python + frontend) qui réunit **tout** au même endroit :

- **Analyse du CCTP par Claude** (API Anthropic) : dépôt du PDF/Word/TXT → contexte + points d'attention.
- **Import Excel Dell Solutions Configurator** : classement automatique + nomenclature.
- **Saisie des équipements** (serveurs, stockage, switches, sauvegarde, logiciels), solution proposée, images, schéma d'architecture.
- **Génération du document Word ONE ID** (modèle, argumentaires sourcés, mise en forme, images) — directement depuis l'interface.
- **Éditeur de schémas draw.io intégré** (100 % local) : dessin du schéma d'architecture directement dans l'interface, inséré automatiquement dans le Word.

## Prérequis

- **Docker Desktop** installé et démarré (Windows).
- Une **clé API Anthropic** : https://console.anthropic.com/ → API Keys.

## Installation (une seule fois)

1. Ouvrir un terminal dans le dossier `app\` :
   ```
   cd "C:\Projets\Appel D'offre\app"
   ```
2. Créer le fichier de configuration `.env` à partir du modèle :
   ```
   copy .env.example .env
   ```
   Puis ouvrir `.env` et coller votre clé : `ANTHROPIC_API_KEY=sk-ant-...`
3. Construire et démarrer le conteneur :
   ```
   docker compose up -d --build
   ```

## Utilisation

- Ouvrir le navigateur sur **http://localhost:8080**
- Onglet **CCTP & Contexte** : déposer le CCTP → « Analyser le CCTP avec Claude » → contexte + points d'attention remplis.
- Onglet **Équipements** : importer l'Excel Dell ou saisir manuellement, renseigner la solution proposée, déposer les images.
- Bouton **« Générer le Word ONE ID »** : le document est téléchargé et enregistré dans `Documents_Generes\`.

### Schéma d'architecture (draw.io)

- Étape **CCTP & Contexte** → section **Schéma d'architecture** → bouton **« ✏️ Dessiner (draw.io) »**.
- L'éditeur draw.io s'ouvre en plein écran. Dessinez, puis cliquez sur **Enregistrer** (disquette) : le schéma est ajouté aux images d'architecture (vignette) et sera inséré dans le chapitre « Architecture proposée » du Word.
- Le schéma reste **ré-éditable** : cliquez sur **✏️** sur sa vignette pour le rouvrir dans draw.io.
- draw.io tourne dans son propre conteneur, accessible directement sur **http://localhost:8081** si besoin. Aucune donnée n'est envoyée à l'extérieur.

## Données partagées avec le dossier projet

Le conteneur monte (en lecture/écriture) les dossiers du projet :

| Hôte (Windows) | Conteneur | Rôle |
|---|---|---|
| `..\Documentation_Constructeur` | `/data/Documentation_Constructeur` | Argumentaires + images produit |
| `..\Fiches_Specs` | `/data/Fiches_Specs` | Fiches de specs |
| `..\Documents_Generes` | `/data/Documents_Generes` | Documents Word générés |

Le modèle Word et l'image de présentation ONE ID sont embarqués dans `app\assets\`.

Deux services sont démarrés : l'application (**port 8080**) et l'éditeur **draw.io** (**port 8081**, image officielle `jgraph/drawio:30.3.6`). Le premier `docker compose up -d` télécharge l'image draw.io (nécessite Internet une seule fois) ; ensuite tout fonctionne hors-ligne.

## Commandes utiles

```
docker compose up -d --build     # construire + démarrer
docker compose logs -f           # voir les logs
docker compose down              # arrêter
docker compose up -d --build     # reconstruire après une modification
```

## Sécurité

- La clé API reste dans `.env` (non inclus dans l'image grâce à `.dockerignore`).
- L'application n'est exposée que sur `localhost` (port 8080).
- Modèle Claude configurable via `ANTHROPIC_MODEL` dans `.env`.

## Dépannage

- **« ANTHROPIC_API_KEY non configurée »** : vérifiez le fichier `.env` puis `docker compose up -d` à nouveau.
- **Page inaccessible** : `docker compose logs -f` pour voir l'erreur ; vérifiez que le port 8080 est libre.
- **PDF scanné** (image) : l'extraction de texte peut être vide ; fournissez un PDF avec texte ou collez le texte.
