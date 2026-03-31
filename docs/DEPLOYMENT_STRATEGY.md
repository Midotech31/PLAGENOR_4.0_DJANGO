# PLAGENOR 4.0 - 100% Free Deployment Strategy

## Overview

This guide provides a **completely free** deployment strategy for PLAGENOR 4.0, optimized for **cloud testing first, then self-hosting migration later**.

---

## 🎯 Your Deployment Plan

```
Phase 1: Cloud Testing (Now)
    ↓
Phase 2: Production Cloud (Optional)
    ↓
Phase 3: Self-Host Migration (Future)
```

---

## 🆓 Recommended Free Stack

| Component | Cloud Option | Self-Host Option | Cost |
|-----------|-------------|------------------|------|
| **Server** | Railway/Render | Your work machine | $0 |
| **Database** | Railway PostgreSQL | PostgreSQL on server | $0 |
| **Domain** | Free subdomain | Your domain | $0 |
| **SSL** | Auto (included) | Let's Encrypt | $0 |
| **CDN** | Cloudflare Free | Optional | $0 |
| **Email** | Gmail App Password | Gmail/SMTP | $0 |
| **Monitoring** | Sentry Free | Sentry Free | $0 |

---

## PHASE 1: Cloud Testing (Now) - Recommended Options

### Option 1: Railway.app ⭐ (Easiest)

**Why Railway?**
- **No credit card required** (for $5 credit signup)
- **$5 free credit/month**
- **Easiest deployment** - Git push to deploy
- **PostgreSQL included**
- **Easy to migrate later**

#### Steps
```bash
# 1. Sign up at https://railway.app
# 2. Install CLI
npm install -g @railway/cli

# 3. Login
railway login

# 4. Initialize project
cd /path/to/plagenor
railway init
railway add postgresql

# 5. Deploy
railway up
# Select: Python > Django

# 6. Set environment
railway variables set SECRET_KEY="your-generated-key"
railway variables set DEBUG="False"
railway variables set ALLOWED_HOSTS="your-railway-url.railway.app"
```

#### Get PostgreSQL URL
```bash
railway variables get DATABASE_URL
```

#### Advantages
- ✅ Zero configuration
- ✅ Auto HTTPS
- ✅ Git deploy
- ✅ PostgreSQL included
- ✅ Easy to migrate out

---

### Option 2: Render.com (Most Features)

**Why Render?**
- **Free tier**: 750 hours/month
- **PostgreSQL free tier**: 1GB storage
- **Auto SSL certificates**
- **GitHub integration**

#### Steps
1. Go to https://render.com
2. Connect GitHub repository
3. Create PostgreSQL database (New → PostgreSQL)
4. Create Web Service (New → Web Service)
   - Build Command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - Start Command: `gunicorn plagenor.wsgi:application`

#### Set Environment Variables
```
SECRET_KEY=generated-key
DEBUG=False
ALLOWED_HOSTS=your-app.onrender.com
DATABASE_URL=from-postgresql-service
```

---

### Option 3: Fly.io (Docker-based)

**Why Fly.io?**
- **3 shared VMs free**
- **Global edge deployment**
- **Docker support**
- **Easy migration to self-hosting**

#### Steps
```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh

# 2. Login
fly auth login

# 3. Create app
fly launch

# 4. Add PostgreSQL
fly postgres create --name plagenor-db
fly postgres attach --name plagenor-db

# 5. Deploy
fly deploy
```

---

## PHASE 2: Production Cloud (Optional)

### Oracle Cloud Always Free (Permanent Free)

**Why Oracle Cloud?**
- **Always free** - doesn't expire
- **2 VMs** with ARM processors
- **6GB RAM per VM**
- **200GB storage per VM**

#### Setup
```bash
# 1. Create account at https://oracle.com/cloud/free
# 2. Create Always Free instance
#    - Shape: Ampere Altra
#    - RAM: 6GB
#    - Storage: 200GB

# 3. SSH and install
ssh opc@<your-ip>
sudo apt update && sudo apt upgrade -y

# 4. Install
sudo apt install -y python3.11 postgresql redis-server nginx certbot

# 5. Deploy app
cd /opt/plagenor
# ... same as self-host deployment
```

---

## PHASE 3: Self-Host Migration (Future)

### From Railway/Render to Self-Host

#### 1. Export Data
```bash
# On cloud (Railway/Render)
python manage.py dumpdata > backup.json
```

#### 2. Setup New Server
```bash
# Your work machine
sudo apt install -y python3.11 postgresql redis-server nginx
```

#### 3. Create Database
```bash
sudo -u postgres psql
CREATE DATABASE plagenor;
CREATE USER plagenor WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE plagenor TO plagenor;
\q
```

#### 4. Import Data
```bash
# On new server
python manage.py loaddata backup.json
```

#### 5. Update Environment
```bash
# Update .env
DATABASE_URL=postgresql://plagenor:password@localhost:5432/plagenor
DEBUG=False
ALLOWED_HOSTS=your-domain.com
```

#### 6. Deploy
```bash
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl start plagenor
```

---

## Complete Migration Checklist

### Cloud → Self-Host
```
1. Export data: dumpdata
2. Export media: rsync -avz
3. Setup PostgreSQL on new server
4. Import data: loaddata
5. Copy media files
6. Update environment variables
7. Run migrations
8. Configure Nginx + SSL
9. Test thoroughly
10. Switch DNS
```

---

## Free Services Summary

| Purpose | Service | Link | Notes |
|---------|---------|------|-------|
| **Testing Cloud** | Railway | railway.app | $5 credit, no CC |
| **Production Cloud** | Oracle Cloud | oracle.com/cloud/free | Always free |
| **Database (Cloud)** | Railway PostgreSQL | Included | 1GB free |
| **Database (Self)** | PostgreSQL | apt install | Unlimited |
| **SSL** | Let's Encrypt | certbot | Auto-renew |
| **Domain** | Many registrars | - | ~$10/year |
| **Email** | Gmail | - | Free with 2FA |
| **Monitoring** | Sentry | sentry.io | 5k events/mo |
| **Uptime** | UptimeRobot | uptimerobot.com | 50 monitors |
| **CDN** | Cloudflare | cloudflare.com | Free tier |

---

## Quick Start Commands

### Railway (Fastest Setup)
```bash
# Install
npm install -g @railway/cli

# Deploy
railway login
cd plagenor
railway init
railway add postgresql
railway up

# Configure
railway variables set SECRET_KEY="$(openssl rand -base64 50)"
railway variables set DEBUG=False
railway variables set ALLOWED_HOSTS="$(railway variables get RAILWAY_STATIC_URL)"
```

### Render
```bash
# 1. Connect GitHub
# 2. Create PostgreSQL
# 3. Create Web Service
# 4. Set env vars
# 5. Deploy
```

---

## Environment Variables Template

```bash
# Essential
SECRET_KEY=generated-50-char-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com

# Database (from Railway/Render/Oracle)
DATABASE_URL=postgresql://...

# Redis (optional for cloud)
REDIS_URL=redis://localhost:6379/0

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=app-password

# Monitoring (optional)
SENTRY_DSN=https://...@sentry.io/...

# Security
CSRF_TRUSTED_ORIGINS=https://your-domain.com
```

---

## Self-Host on Work Machine (Future)

### Minimum Requirements
- **OS**: Ubuntu 22.04 LTS
- **RAM**: 4GB
- **Storage**: 50GB
- **CPU**: 2 cores

### Quick Setup
```bash
# 1. Install
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 postgresql redis-server nginx certbot

# 2. Database
sudo -u postgres psql -c "CREATE DATABASE plagenor;"
sudo -u postgres psql -c "CREATE USER plagenor WITH PASSWORD 'password';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE plagenor TO plagenor;"

# 3. App
cd /opt/plagenor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Configure
cp .env.production .env
# Edit .env

# 5. Deploy
python manage.py migrate
python manage.py collectstatic --noinput
sudo cp deploy/plagenor.service /etc/systemd/system/
sudo systemctl enable plagenor && sudo systemctl start plagenor
sudo certbot --nginx -d your-domain.com
```

---

## Troubleshooting

### Railway
```bash
# View logs
railway logs

# Open shell
railway shell

# Check variables
railway variables
```

### Render
```bash
# View logs
render logs

# Connect to shell
render ssh
```

---

## Recommended Path

```
Week 1: Railway (5 min setup)
    ↓
Test for 1-2 weeks
    ↓
If happy: Oracle Cloud (permanent free)
    ↓
Or: Your work machine (self-host)
```

**Start with Railway for fastest testing, migrate when ready!** 🚀

---

**Total cost: $0**
