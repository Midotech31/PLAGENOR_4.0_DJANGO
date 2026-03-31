# 🚀 PLAGENOR 4.0 - Railway Setup Complete

## ✅ Changes Made

### 1. Updated Procfile
```bash
web: sh -c "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn plagenor.wsgi:application"
```
**What it does:** Runs migrations and collects static files automatically before starting the app.

### 2. Created railway.json
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python manage.py migrate --noinput && gunicorn plagenor.wsgi:application --bind :$PORT --workers 2"
  }
}
```

### 3. Updated settings.py
- Added `plagenor.up.railway.app` to ALLOWED_HOSTS
- Added `https://plagenor.up.railway.app` to CSRF_TRUSTED_ORIGINS
- Settings already support DATABASE_URL from environment

## 🎯 What You Need to Do in Railway

### Option A: Use Railway AI Chat

**Say this to Railway AI:**
> "My Django app needs to connect to the PostgreSQL database. I need you to:
> 1. Add a DATABASE_URL environment variable to my app service that references the PostgreSQL service
> 2. Redeploy the app
> 3. Run migrations automatically on deploy"

### Option B: Manual Setup

1. **Go to Railway Dashboard:**
   - https://railway.app/dashboard

2. **Connect Database to App:**
   - Click on your **Django app service** (not PostgreSQL)
   - Go to **Settings** → **Environment**
   - Click **New Variable**
   - Name: `DATABASE_URL`
   - Value: Click **Reference** and select your PostgreSQL service's `DATABASE_URL`
   - Save

3. **Set Production Variables:**
   In the same Environment section, add:
   ```
   DEBUG=False
   SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(50))">
   ALLOWED_HOSTS=plagenor.up.railway.app
   ```

4. **Redeploy:**
   - Go to **Deployments** tab
   - Click **Redeploy** on the latest deployment

5. **Check Logs:**
   - Click on the deployment
   - Look for "Running migrations..." in the logs
   - Should see "Migrations applied successfully"

## 📋 Pre-Deploy Checklist

Before deploying, verify these in Railway:

- [ ] **DATABASE_URL** set (references PostgreSQL service)
- [ ] **DEBUG=False** (for production)
- [ ] **SECRET_KEY** strong (not default)
- [ ] **ALLOWED_HOSTS** includes `plagenor.up.railway.app`

## 🔍 Verify Deployment

After setup, check:

1. **Homepage:** https://plagenor.up.railway.app/
2. **Admin Panel:** https://plagenor.up.railway.app/admin/
3. **Static Files:** Should load without /app/staticfiles/ warning
4. **Database:** No connection errors in logs

## 📝 Railway CLI Commands

```bash
# Connect to Railway
railway login
railway link

# Check variables
railway variables

# View logs
railway logs

# Run migrations manually
railway run python manage.py migrate

# Create superuser
railway run python manage.py createsuperuser

# Open shell
railway run python manage.py shell
```

## 🆘 If Issues Persist

### Database Connection Error
**Symptom:** `django.db.utils.OperationalError: could not connect to server`

**Fix:** 
1. Go to Railway dashboard
2. Select PostgreSQL service
3. Copy the connection string
4. Paste as DATABASE_URL in app service

### Static Files 404
**Symptom:** CSS/JS not loading

**Fix:**
```bash
railway run python manage.py collectstatic --noinput
```

### Migrations Not Applied
**Fix:**
```bash
railway run python manage.py migrate
```

### 500 Error
**Fix:** Check Railway logs for the specific error:
```bash
railway logs
```

## ✅ Expected Final State

- ✅ App accessible at https://plagenor.up.railway.app/
- ✅ Database connected and working
- ✅ Migrations applied automatically
- ✅ Static files served correctly
- ✅ HTTPS enabled
- ✅ Admin panel at /admin/ accessible
