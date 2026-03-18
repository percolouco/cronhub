# Synchronisation Gitea → GitHub

Ce dossier contient les scripts pour synchroniser automatiquement tous les dépôts Gitea vers GitHub.

## 📋 Description

Le système synchronise tous les dépôts de l'utilisateur `perco` depuis le serveur Gitea (`http://192.168.1.29:3500`) vers le compte GitHub `percolouco`, en mode mirror (toutes les branches et tags).

## 🔑 Configuration des secrets

Les tokens d'accès doivent être configurés comme secrets dans le Cursor Dashboard (Cloud Agents > Secrets) :

1. **GITHUB_TOKEN** (requis)
   - Token d'accès personnel GitHub avec les permissions `repo`
   - Générer sur : https://github.com/settings/tokens
   - Scopes nécessaires : `repo`, `workflow`

2. **GITEA_TOKEN** (optionnel mais recommandé)
   - Token d'accès Gitea pour les dépôts privés
   - Générer sur : http://192.168.1.29:3500/user/settings/applications

## 📂 Fichiers

- **`sync_gitea_to_github.py`** : Script principal de synchronisation
- **`init_sync_job.py`** : Script d'initialisation du cron job dans CronHub
- **`README_SYNC.md`** : Ce fichier

## 🚀 Installation

### 1. Configurer les secrets

Dans le Cursor Dashboard :
- Allez dans Cloud Agents > Secrets
- Ajoutez `GITHUB_TOKEN` avec votre token GitHub
- Ajoutez `GITEA_TOKEN` avec votre token Gitea (optionnel)

### 2. Initialiser le cron job

Exécutez le script d'initialisation pour créer le job dans CronHub :

```bash
python3 /opt/container/cronhub/scripts/init_sync_job.py
```

Le job sera configuré pour s'exécuter **toutes les heures** (schedule cron : `0 * * * *`).

### 3. Vérifier

Accédez à CronHub pour vérifier que le job a été créé :
- URL : https://cronhub.nas.percolouco.com
- Nom du job : "Sync Gitea → GitHub"
- Catégorie : "sync"

## 🔧 Fonctionnement

Le script effectue les opérations suivantes :

1. **Liste les dépôts Gitea** via l'API Gitea (`/api/v1/user/repos`)
2. Pour chaque dépôt :
   - Vérifie si le dépôt existe sur GitHub
   - Crée le dépôt sur GitHub s'il n'existe pas
   - Clone le dépôt Gitea en mode `--mirror` (toutes les branches et tags)
   - Push en mode `--mirror` vers GitHub
3. **Affiche un résumé** avec le nombre de réussites/échecs

## 📊 Logs et monitoring

Les logs d'exécution sont disponibles dans CronHub :
- Accédez au détail du job "Sync Gitea → GitHub"
- Consultez l'historique des exécutions
- Stdout/stderr sont capturés pour chaque exécution

## 🧪 Test manuel

Pour tester le script manuellement (hors cron) :

```bash
# Définir les tokens temporairement
export GITHUB_TOKEN="votre_token_github"
export GITEA_TOKEN="votre_token_gitea"

# Exécuter le script
python3 /opt/container/cronhub/scripts/sync_gitea_to_github.py
```

Ou via CronHub, en utilisant le bouton "Run Now" sur la page de détail du job.

## 📝 Notes importantes

- **Mode mirror** : Synchronise TOUTES les branches et tags (pas seulement `main`)
- **Dépôts privés** : Les dépôts privés sur Gitea restent privés sur GitHub
- **Timeout** : Chaque opération git a un timeout de 5 minutes (300s)
- **Exécution via nsenter** : Le script s'exécute dans le namespace de l'hôte Docker pour accès à git et python3

## 🔍 Dépannage

### Le script échoue avec "GITHUB_TOKEN non défini"

Vérifiez que le secret `GITHUB_TOKEN` est bien configuré dans le Cursor Dashboard et qu'il est injecté dans l'environnement du container CronHub.

### Erreur lors du clone Gitea

Vérifiez que :
- Le serveur Gitea est accessible (`http://192.168.1.29:3500`)
- Le token Gitea est valide (pour les dépôts privés)
- L'utilisateur `perco` existe et a des dépôts

### Erreur lors du push GitHub

Vérifiez que :
- Le token GitHub a les bonnes permissions (`repo`, `workflow`)
- Le compte GitHub `percolouco` existe
- Il n'y a pas de limite de taille de dépôt atteinte

## 📅 Modification du planning

Pour changer la fréquence de synchronisation :

1. Éditez le job dans CronHub (interface web ou API)
2. Modifiez le champ `schedule` avec une nouvelle expression cron :
   - Toutes les heures : `0 * * * *` (actuel)
   - Toutes les 2 heures : `0 */2 * * *`
   - Tous les jours à 3h : `0 3 * * *`
   - Toutes les 30 minutes : `*/30 * * * *`

## 📄 Licence

Projet privé — perco / NAS domestique
