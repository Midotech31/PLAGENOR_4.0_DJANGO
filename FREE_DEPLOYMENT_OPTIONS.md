# PLAGENOR 4.0 - All Free Deployment Options

## Option 1: Render.com (Easiest Alternative)

**Why Render?**
- ✅ **Free tier**: 750 hours/month
- ✅ **PostgreSQL free tier**: 1GB storage
- ✅ **No credit card required**
- ✅ **Auto SSL certificates**
- ✅ **GitHub integration**

### Steps:
1. Go to https://render.com
2. Sign up with GitHub account
3. Click "New" → "PostgreSQL"
   - Name: `plagenor-db`
   - Region: Frankfurt (EU)
   - Click "Create Database"
4. Click "New" → "Web Service"
   - Connect your GitHub repo
   - Name: `plagenor-4`
   - Environment: Python 3
   - Build Command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - Start Command: `gunicorn plagenor.wsgi:application`
5. Add Environment Variables:
   - `SECRET_KEY`: generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `DEBUG`: `False`
   - `DATABASE_URL`: (copy from PostgreSQL service)
6. Click "Create Web Service"

---

## Option 2: Fly.io (Docker-based)

**Why Fly.io?**
- ✅ **$5 free credit/month**
- ✅ **3 shared VMs free**
- ✅ **Global edge deployment**

### Steps:
```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Launch app
fly launch

# Add PostgreSQL
fly postgres create --name plagenor-db
fly postgres attach --name plagenor-db

# Deploy
fly deploy
```

---

## Option 3: Oracle Cloud Always Free (Most Powerful)

**Why Oracle Cloud?**
- ✅ **Always free** - never expires
- ✅ **6GB RAM, 200GB storage**
- ✅ **Full control like self-hosting**
- ✅ **Good for learning self-hosting**

### Steps:
1. Go to https://oracle.com/cloud/free
2. Create account
3. Create Always Free instance:
   - Shape: Ampere Altra (ARM)
   - RAM: 6GB
   - Storage: 200GB
   - OS: Ubuntu 22.04
4. SSH into instance and run setup commands (see `docs/DEPLOYMENT_STRATEGY.md`)

---

## Option 4: PythonAnywhere (Simplest)

**Why PythonAnywhere?**
- ✅ **Beginner friendly**
- ✅ **Free tier available**
- ✅ **Web-based interface**

### Steps:
1. Go to https://pythonanywhere.com
2. Create free account
3. Upload files via web interface
4. Set up virtual environment
5. Configure WSGI file
6. Reload web app

---

## Comparison

| Platform | RAM | Storage | Database | SSL | Ease |
|----------|-----|---------|----------|-----|------|
| **Railway** | Shared | 1GB | ✅ Included | ✅ Auto | ⭐⭐⭐ |
| **Render** | 512MB | 1GB | ✅ Included | ✅ Auto | ⭐⭐⭐⭐ |
| **Fly.io** | Shared | - | ✅ Included | ✅ Auto | ⭐⭐⭐ |
| **Oracle** | 6GB | 200GB | ❌ Self-setup | ✅ Let's Encrypt | ⭐⭐ |
| **PythonAnywhere** | Limited | Limited | ✅ SQLite | ✅ Yes | ⭐⭐⭐⭐⭐ |

---

## Recommendation

**For fastest deployment:** Use **Render.com**
- No CLI needed
- Web interface only
- PostgreSQL included
- Auto HTTPS

**Start here:** https://render.com
