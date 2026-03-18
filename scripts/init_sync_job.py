#!/usr/bin/env python3
"""
Script d'initialisation du job de synchronisation Gitea → GitHub dans CronHub
Crée ou met à jour le cron job pour une exécution toutes les heures
"""

import json
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Configuration
CRONHUB_URL = "https://cronhub.nas.percolouco.com"
JOB_NAME = "Sync Gitea → GitHub"
JOB_CATEGORY = "sync"
JOB_SCHEDULE = "0 * * * *"  # Toutes les heures à la minute 0
JOB_COMMAND = "nsenter --target 1 --mount --uts --ipc --net --pid -- python3 /opt/container/cronhub/scripts/sync_gitea_to_github.py"
JOB_DESCRIPTION = "Synchronisation automatique des dépôts Gitea (http://192.168.1.29:3500/perco) vers GitHub (percolouco)"

def log(message):
    """Affiche un message"""
    print(f"[INFO] {message}")

def api_request(url, method="GET", data=None):
    """Effectue une requête HTTP vers l'API CronHub"""
    headers = {"Content-Type": "application/json"}
    if data:
        data = json.dumps(data).encode('utf-8')
    
    req = Request(url, headers=headers, data=data, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as e:
        error_msg = e.read().decode('utf-8')
        log(f"Erreur HTTP {e.code} pour {url}: {error_msg}")
        return None
    except URLError as e:
        log(f"Erreur URL pour {url}: {e.reason}")
        return None

def find_existing_job():
    """Cherche si un job avec le même nom existe déjà"""
    log(f"Recherche d'un job existant nommé '{JOB_NAME}'...")
    url = f"{CRONHUB_URL}/api/jobs"
    jobs = api_request(url)
    
    if jobs is None:
        log("Impossible de récupérer la liste des jobs")
        return None
    
    for job in jobs:
        if job.get("name") == JOB_NAME:
            log(f"Job existant trouvé: ID={job['id']}")
            return job
    
    log("Aucun job existant trouvé")
    return None

def create_job():
    """Crée un nouveau job dans CronHub"""
    log("Création d'un nouveau job...")
    url = f"{CRONHUB_URL}/api/jobs"
    data = {
        "name": JOB_NAME,
        "schedule": JOB_SCHEDULE,
        "command": JOB_COMMAND,
        "description": JOB_DESCRIPTION,
        "category": JOB_CATEGORY,
        "enabled": True
    }
    
    result = api_request(url, method="POST", data=data)
    if result:
        log(f"✓ Job créé avec succès: ID={result['id']}")
        return True
    else:
        log("✗ Échec de la création du job")
        return False

def update_job(job_id):
    """Met à jour un job existant dans CronHub"""
    log(f"Mise à jour du job existant: ID={job_id}")
    url = f"{CRONHUB_URL}/api/jobs/{job_id}"
    data = {
        "name": JOB_NAME,
        "schedule": JOB_SCHEDULE,
        "command": JOB_COMMAND,
        "description": JOB_DESCRIPTION,
        "category": JOB_CATEGORY,
        "enabled": True
    }
    
    result = api_request(url, method="PUT", data=data)
    if result:
        log(f"✓ Job mis à jour avec succès")
        return True
    else:
        log("✗ Échec de la mise à jour du job")
        return False

def main():
    """Fonction principale"""
    log("=== Initialisation du job de synchronisation Gitea → GitHub ===")
    
    # Vérifier si le job existe déjà
    existing_job = find_existing_job()
    
    if existing_job:
        # Mettre à jour le job existant
        success = update_job(existing_job["id"])
    else:
        # Créer un nouveau job
        success = create_job()
    
    if success:
        log("=== Configuration terminée avec succès ===")
        log(f"Le job s'exécutera toutes les heures (schedule: {JOB_SCHEDULE})")
        log(f"Vérifiez sur {CRONHUB_URL}")
        sys.exit(0)
    else:
        log("=== Échec de la configuration ===")
        sys.exit(1)

if __name__ == "__main__":
    main()
