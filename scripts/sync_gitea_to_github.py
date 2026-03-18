#!/usr/bin/env python3
"""
Script de synchronisation des dépôts Gitea vers GitHub
Synchronise tous les dépôts depuis http://192.168.1.29:3500/perco vers GitHub (percolouco)
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Configuration
GITEA_URL = "http://192.168.1.29:3500"
GITEA_USER = "perco"
GITHUB_USER = "percolouco"

# Les tokens doivent être configurés comme secrets dans Cursor Dashboard
GITEA_TOKEN = os.environ.get("GITEA_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

def log(message):
    """Affiche un message avec timestamp"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def api_request(url, token=None, method="GET", data=None):
    """Effectue une requête HTTP avec gestion du token"""
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    if data:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode('utf-8')
    
    req = Request(url, headers=headers, data=data, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as e:
        log(f"Erreur HTTP {e.code} pour {url}: {e.read().decode('utf-8')}")
        return None
    except URLError as e:
        log(f"Erreur URL pour {url}: {e.reason}")
        return None

def get_gitea_repos():
    """Liste tous les dépôts de l'utilisateur Gitea"""
    log(f"Récupération des dépôts Gitea pour {GITEA_USER}...")
    url = f"{GITEA_URL}/api/v1/user/repos"
    repos = api_request(url, token=GITEA_TOKEN)
    
    if repos is None:
        log("Erreur lors de la récupération des dépôts Gitea")
        return []
    
    log(f"Trouvé {len(repos)} dépôts Gitea")
    return repos

def github_repo_exists(repo_name):
    """Vérifie si un dépôt existe sur GitHub"""
    url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}"
    result = api_request(url, token=GITHUB_TOKEN)
    return result is not None

def create_github_repo(repo_name, description="", is_private=False):
    """Crée un dépôt sur GitHub"""
    log(f"Création du dépôt GitHub: {repo_name}")
    url = "https://api.github.com/user/repos"
    data = {
        "name": repo_name,
        "description": description,
        "private": is_private,
        "auto_init": False
    }
    result = api_request(url, token=GITHUB_TOKEN, method="POST", data=data)
    return result is not None

def sync_repo(gitea_repo):
    """Synchronise un dépôt Gitea vers GitHub en mode mirror"""
    repo_name = gitea_repo["name"]
    log(f"Début de la synchronisation: {repo_name}")
    
    # Construire l'URL clone avec token
    clone_url = gitea_repo["clone_url"]
    if GITEA_TOKEN:
        # Insérer le token dans l'URL
        clone_url = clone_url.replace("http://", f"http://oauth2:{GITEA_TOKEN}@")
    
    # URL GitHub avec token
    github_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{repo_name}.git"
    
    # Créer le dépôt GitHub s'il n'existe pas
    if not github_repo_exists(repo_name):
        description = gitea_repo.get("description", "")
        is_private = gitea_repo.get("private", False)
        if not create_github_repo(repo_name, description, is_private):
            log(f"Échec de la création du dépôt GitHub: {repo_name}")
            return False
    
    # Créer un répertoire temporaire
    temp_dir = tempfile.mkdtemp(prefix=f"gitea_sync_{repo_name}_")
    
    try:
        log(f"Clone mirror depuis Gitea: {repo_name}")
        # Clone en mode mirror
        result = subprocess.run(
            ["git", "clone", "--mirror", clone_url, temp_dir],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            log(f"Erreur lors du clone: {result.stderr}")
            return False
        
        log(f"Push mirror vers GitHub: {repo_name}")
        # Push en mode mirror vers GitHub
        result = subprocess.run(
            ["git", "push", "--mirror", github_url],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            log(f"Erreur lors du push: {result.stderr}")
            return False
        
        log(f"✓ Synchronisation réussie: {repo_name}")
        return True
        
    except subprocess.TimeoutExpired:
        log(f"Timeout lors de la synchronisation de {repo_name}")
        return False
    except Exception as e:
        log(f"Erreur lors de la synchronisation de {repo_name}: {e}")
        return False
    finally:
        # Nettoyer le répertoire temporaire
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            log(f"Erreur lors du nettoyage de {temp_dir}: {e}")

def main():
    """Fonction principale"""
    log("=== Début de la synchronisation Gitea → GitHub ===")
    
    # Vérifier les tokens
    if not GITEA_TOKEN:
        log("ATTENTION: GITEA_TOKEN non défini, l'accès aux dépôts privés peut échouer")
    if not GITHUB_TOKEN:
        log("ERREUR: GITHUB_TOKEN non défini (requis)")
        sys.exit(1)
    
    # Récupérer la liste des dépôts
    repos = get_gitea_repos()
    if not repos:
        log("Aucun dépôt à synchroniser")
        return
    
    # Synchroniser chaque dépôt
    success_count = 0
    fail_count = 0
    
    for repo in repos:
        if sync_repo(repo):
            success_count += 1
        else:
            fail_count += 1
    
    # Résumé
    log("=== Synchronisation terminée ===")
    log(f"Réussis: {success_count}/{len(repos)}")
    log(f"Échecs: {fail_count}/{len(repos)}")
    
    if fail_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
