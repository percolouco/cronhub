# 🕐 CronHub

**CronHub** est un gestionnaire de cron jobs avec interface web et API REST, auto-hébergé sur NAS.

🌐 **URL** : [https://cronhub.nas.percolouco.com](https://cronhub.nas.percolouco.com)

---

## 📋 Description

CronHub permet de créer, gérer et monitorer des tâches planifiées (cron jobs) depuis une interface web simple et intuitive. Chaque job est exécuté via `subprocess` dans le conteneur Docker, avec capture des logs (stdout/stderr) et historique d'exécution.

---

## 🛠️ Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend / API | [FastAPI](https://fastapi.tiangolo.com/) |
| Scheduler | [APScheduler 3.x](https://apscheduler.readthedocs.io/) |
| Base de données | SQLite (WAL mode) |
| Templates UI | Jinja2 |
| CSS | Tailwind CSS (via CDN) + styles custom |
| Serveur ASGI | Uvicorn |
| Containerisation | Docker |

---

## ✨ Fonctionnalités

- **CRUD complet** — Créer, lire, modifier, supprimer des jobs
- **Toggle actif/inactif** — Activer ou désactiver un job sans le supprimer
- **Run immédiat** — Déclencher un job manuellement hors schedule
- **Logs d'exécution** — Historique complet avec stdout, stderr, exit code, durée
- **Statuts visuels** — Dashboard avec compteurs (total, actifs, succès, échecs)
- **API Swagger** — Documentation interactive disponible sur `/docs`
- **Timezone** — Europe/Paris (configurable via `TZ`)
- **Persistance** — SQLite dans volume Docker `/data`

---

## 🔌 API Endpoints

### Santé
| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/api/health` | Vérification de l'état de l'API |

### Jobs
| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/api/jobs` | Lister tous les jobs |
| `POST` | `/api/jobs` | Créer un job |
| `GET` | `/api/jobs/{id}` | Détail d'un job |
| `PUT` | `/api/jobs/{id}` | Modifier un job |
| `DELETE` | `/api/jobs/{id}` | Supprimer un job |
| `POST` | `/api/jobs/{id}/toggle` | Activer/désactiver un job |
| `POST` | `/api/jobs/{id}/run` | Déclencher un job manuellement |
| `GET` | `/api/jobs/{id}/logs` | Logs d'exécution d'un job |

### UI (HTML)
| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/` | Dashboard principal |
| `GET` | `/jobs/new` | Formulaire création |
| `GET` | `/jobs/{id}` | Détail + logs UI |
| `GET` | `/jobs/{id}/edit` | Formulaire édition |
| `POST` | `/jobs/{id}/run-now` | Run immédiat (UI) |
| `GET` | `/docs` | Documentation Swagger |

### Exemple d'appel API

```bash
# Créer un job
curl -X POST https://cronhub.nas.percolouco.com/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mon backup",
    "schedule": "0 3 * * *",
    "command": "/scripts/backup.sh",
    "description": "Backup quotidien à 3h",
    "enabled": true
  }'

# Lister les jobs
curl https://cronhub.nas.percolouco.com/api/jobs

# Déclencher manuellement
curl -X POST https://cronhub.nas.percolouco.com/api/jobs/{id}/run

# Consulter les logs
curl https://cronhub.nas.percolouco.com/api/jobs/{id}/logs?limit=20
```

---

## 🗂️ Structure du projet

```
cronhub/
├── app/
│   ├── __init__.py
│   └── main.py          # Application FastAPI (routes, scheduler, DB)
├── templates/
│   ├── index.html       # Dashboard
│   ├── job_detail.html  # Détail d'un job + logs
│   └── job_form.html    # Formulaire création/édition
├── data/                # Volume persistant (SQLite)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 🐳 Installation Docker

### Prérequis

- Docker + Docker Compose
- (Optionnel) Traefik comme reverse proxy

### docker-compose.yml

```yaml
version: "3.8"

services:
  cronhub:
    build: .
    container_name: cronhub
    restart: unless-stopped
    volumes:
      - ./data:/data                              # Persistance SQLite
      - /opt/container/cronmaster/scripts:/scripts:ro  # Scripts montés en lecture seule
      - /var/run/docker.sock:/var/run/docker.sock # Accès Docker (optionnel)
    environment:
      - DB_PATH=/data/cronhub.db
      - TZ=Europe/Paris
    networks:
      - proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.cronhub.rule=Host(`cronhub.nas.percolouco.com`)"
      - "traefik.http.routers.cronhub.entrypoints=websecure"
      - "traefik.http.routers.cronhub.tls=true"
      - "traefik.http.routers.cronhub.tls.certresolver=letsencrypt"
      - "traefik.http.services.cronhub.loadbalancer.server.port=8000"

networks:
  proxy:
    external: true
```

### Démarrage

```bash
cd /opt/container/cronhub
docker compose up -d --build
```

### Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DB_PATH` | `/data/cronhub.db` | Chemin de la base SQLite |
| `TZ` | `Europe/Paris` | Timezone pour le scheduler |

---

## 📦 Modèle de données

### Job

```json
{
  "id": "uuid",
  "name": "Mon job",
  "schedule": "0 8 * * *",
  "command": "/scripts/mon-script.sh",
  "description": "Description optionnelle",
  "enabled": true,
  "last_run": "2026-03-15T08:00:00",
  "last_status": "success",
  "created_at": "2026-03-01T12:00:00"
}
```

### Log d'exécution

```json
{
  "id": 42,
  "job_id": "uuid",
  "started_at": "2026-03-15T08:00:00",
  "ended_at": "2026-03-15T08:00:01",
  "status": "success",
  "exit_code": 0,
  "stdout": "...",
  "stderr": ""
}
```

---

## 🔧 Notes de déploiement

- Les scripts dans `/scripts` sont montés depuis `/opt/container/cronmaster/scripts` (lecture seule)
- La commande doit être exécutable **depuis l'intérieur du container**
- Le scheduler APScheduler démarre automatiquement au lancement et recharge tous les jobs actifs
- Les jobs sont exécutés en `shell=True` avec un timeout de 3600 secondes
- Stdout/stderr sont limités à 10 000 caractères par exécution

---

## 📄 Licence

Projet privé — perco / NAS domestique
