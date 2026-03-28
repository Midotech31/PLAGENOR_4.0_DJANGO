# PLAGENOR 4.0 — Guide de Déploiement

## Prérequis

- Windows 10/11 ou Windows Server 2019+
- Python 3.11+
- Git
- NSSM (Non-Sucking Service Manager) — https://nssm.cc
- Cloudflare Tunnel (cloudflared) — pour l'accès externe

---

## 1. Installation

```powershell
# Cloner le dépôt
cd C:\Apps
git clone <repo-url> plagenor
cd plagenor

# Créer l'environnement virtuel
python -m venv venv
venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Copier et configurer l'environnement
copy .env.example .env
# Éditer .env avec un SECRET_KEY sécurisé et DEBUG=False

# Créer les répertoires
mkdir data media backups

# Initialiser la base de données
python manage.py migrate
python manage.py createsuperuser

# Collecter les fichiers statiques
python manage.py collectstatic --noinput
```

---

## 2. Démarrage rapide (développement)

```powershell
start_plagenor.bat
```

Accédez à http://localhost:8000

---

## 3. Service Windows avec NSSM

### Option A : Serveur de développement (usage interne léger)

```powershell
nssm install PLAGENOR "C:\Apps\plagenor\venv\Scripts\python.exe" "C:\Apps\plagenor\manage.py" "runserver" "0.0.0.0:8000"
nssm set PLAGENOR AppDirectory "C:\Apps\plagenor"
nssm set PLAGENOR DisplayName "PLAGENOR 4.0"
nssm set PLAGENOR Description "Plateforme de Gestion des Operations Scientifiques"
nssm set PLAGENOR Start SERVICE_AUTO_START
nssm set PLAGENOR AppStdout "C:\Apps\plagenor\logs\service.log"
nssm set PLAGENOR AppStderr "C:\Apps\plagenor\logs\error.log"
nssm start PLAGENOR
```

### Option B : Gunicorn (production recommandée)

```powershell
nssm install PLAGENOR "C:\Apps\plagenor\venv\Scripts\gunicorn.exe" "plagenor.wsgi:application" "--bind" "0.0.0.0:8000" "--workers" "3"
nssm set PLAGENOR AppDirectory "C:\Apps\plagenor"
nssm set PLAGENOR DisplayName "PLAGENOR 4.0"
nssm set PLAGENOR Description "Plateforme de Gestion des Operations Scientifiques"
nssm set PLAGENOR Start SERVICE_AUTO_START
nssm set PLAGENOR AppStdout "C:\Apps\plagenor\logs\service.log"
nssm set PLAGENOR AppStderr "C:\Apps\plagenor\logs\error.log"
nssm start PLAGENOR
```

### Gestion du service

```powershell
nssm start PLAGENOR
nssm stop PLAGENOR
nssm restart PLAGENOR
nssm status PLAGENOR
nssm remove PLAGENOR confirm   # Désinstaller
```

---

## 4. Cloudflare Tunnel (accès externe sécurisé)

### Installation

1. Téléchargez cloudflared : https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
2. Authentifiez-vous :

```powershell
cloudflared tunnel login
```

### Création du tunnel

```powershell
cloudflared tunnel create plagenor
```

### Configuration

Placez `cloudflare/config.yml` dans le dossier `.cloudflared` de l'utilisateur, ou utilisez :

```powershell
cloudflared tunnel --config cloudflare/config.yml run plagenor
```

### Service Cloudflare (NSSM)

```powershell
nssm install CloudflareTunnel "C:\Program Files\cloudflared\cloudflared.exe" "tunnel" "--config" "C:\Apps\plagenor\cloudflare\config.yml" "run" "plagenor"
nssm set CloudflareTunnel Start SERVICE_AUTO_START
nssm start CloudflareTunnel
```

### DNS

Ajoutez un enregistrement CNAME dans Cloudflare DNS :
- **Nom** : `plagenor` (ou votre sous-domaine)
- **Cible** : `<tunnel-id>.cfargotunnel.com`

---

## 5. Sauvegardes

### Manuelle

```powershell
python backup_plagenor.py
```

### Automatique (Planificateur de tâches Windows)

```powershell
schtasks /create /tn "PLAGENOR_Backup" /tr "C:\Apps\plagenor\venv\Scripts\python.exe C:\Apps\plagenor\backup_plagenor.py" /sc daily /st 02:00
```

### Lister les backups

```powershell
python backup_plagenor.py list
```

---

## 6. Configuration .env (Production)

```env
SECRET_KEY=<clé-aléatoire-de-50-caractères>
DEBUG=False
ALLOWED_HOSTS=plagenor.votre-domaine.dz,localhost
LANGUAGE_CODE=fr
IBTIKAR_BUDGET_CAP=200000
VAT_RATE=0.19
INVOICE_PREFIX=GENOCLAB-INV
```

---

## 7. Mise à jour

```powershell
cd C:\Apps\plagenor
nssm stop PLAGENOR
git pull
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
nssm start PLAGENOR
```

---

## 8. Vérification

```powershell
# Vérifier que Django est correctement configuré
python manage.py check --deploy

# Tester l'accès local
curl http://localhost:8000

# Voir les logs
type logs\service.log
type logs\error.log
```

---

## Architecture

```
C:\Apps\plagenor\
├── data\              ← Base SQLite
├── media\             ← Fichiers uploadés (rapports, images)
├── backups\           ← Sauvegardes automatiques
├── logs\              ← Logs du service
├── staticfiles\       ← Fichiers statiques (collectstatic)
├── cloudflare\        ← Configuration tunnel
├── venv\              ← Environnement Python
└── manage.py
```
