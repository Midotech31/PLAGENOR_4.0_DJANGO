# PLAGENOR 4.0 - Production Deployment Checklist

## 🔴 CRITICAL - Must Fix Before Deployment

### Security Settings

| Task | Status | Notes |
|------|--------|-------|
| ✅ Set `DEBUG=False` in `.env` | DONE | Configured in settings.py - automatic when env var is set |
| ✅ Generate strong `SECRET_KEY` | ✅ DONE | Generated below |
| ✅ Configure `ALLOWED_HOSTS` | **TODO** | Add your domain(s) to Railway environment variables |
| ✅ Configure `CSRF_TRUSTED_ORIGINS` | **TODO** | Add your domain with https:// |

**Your Generated SECRET_KEY:**
```
yE9MDgvcSSUJSvFUp-O3SfyBrzj-97X_iFoXNFz654PhWFO8pi2dO7uclAVlcIqSnA4
```

**To generate a new SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### Database

| Task | Status | Notes |
|------|--------|-------|
| ✅ PostgreSQL support | DONE | Already configured with dj-database-url |
| ✅ SQLite for <10 users | OK | Using SQLite in dev, PostgreSQL recommended for prod |
| ⚠️ Configure DATABASE_URL | **TODO** | Set PostgreSQL connection string from your provider |

**Recommended PostgreSQL providers (free tiers):**
- **Railway** - $5/month includes 1 PostgreSQL instance
- **Supabase** - 500MB free
- **Neon** - 3GB free
- **Render** - Free tier available

### Static & Media Files

| Task | Status | Notes |
|------|--------|-------|
| ✅ `collectstatic` in Procfile | DONE | Automatically runs on deploy |
| ✅ Cloud storage support | DONE | Added django-storages + boto3 to requirements.txt |
| ✅ Cloud storage config | DONE | settings.py has Cloudflare R2 / AWS S3 config |
| ⚠️ Configure cloud storage | **TODO** | Set USE_CLOUD_STORAGE=True and add credentials |

**Recommended storage options:**
- ✅ Cloudflare R2 (S3-compatible, cheap) - Configuration ready
- AWS S3
- Supabase Storage

## 🟡 IMPORTANT - Should Fix Soon

### Error Logging

| Task | Status | Notes |
|------|--------|-------|
| ✅ Sentry integration ready | DONE | Already in settings.py |
| ⚠️ Configure Sentry DSN | **TODO** | Sign up at https://sentry.io and add DSN |

```bash
# In your Railway environment variables, add:
SENTRY_DSN=https://[key]@[org].sentry.io/[project]
```

### Backups

| Task | Status | Notes |
|------|--------|-------|
| ✅ Backup script exists | DONE | `core/management/commands/backup_db.py` |
| ✅ Railway backup script | DONE | `backup_railway.sh` created |
| ⚠️ Schedule automated backups | **TODO** | Set up cron job or Railway Cron |

**For Railway PostgreSQL:**
```bash
# Install Railway CLI
npm i -g @railway/cli

# Connect to your project
railway login
railway link

# Run backup manually:
./backup_railway.sh
```

### Rate Limiting

| Task | Status | Notes |
|------|--------|-------|
| ✅ Rate limiting implemented | DONE | `plagenor/rate_limit.py` - active by default |
| ✅ Brute force protection | DONE | 5 failed attempts = 15 min lockout |

### CSRF Protection

| Task | Status | Notes |
|------|--------|-------|
| ✅ CSRF_COOKIE_SECURE | DONE | Enabled when DEBUG=False in settings.py |
| ✅ CSRF_TRUSTED_ORIGINS | DONE | Already configured in settings.py |

## 🟢 RECOMMENDED IMPROVEMENTS

### Performance

| Task | Status | Notes |
|------|--------|-------|
| ✅ Redis caching support | DONE | Configure REDIS_URL to enable |
| ✅ Static file serving | DONE | Whitenoise with compression |
| ⚠️ Database query optimization | Ongoing | Already using select_related/prefetch_related |
| ⚠️ Static file CDN | **TODO** | Use Cloudflare (free tier) for static assets |

### Monitoring

| Task | Status | Notes |
|------|--------|-------|
| ✅ Health check endpoint | DONE | `/health/` returns status JSON |
| ✅ Monitoring config | DONE | `monitoring.yaml` with UptimeRobot settings |
| ⚠️ Uptime monitoring setup | **TODO** | Create free UptimeRobot account and add monitors |
| ⚠️ Error tracking | **TODO** | Sentry already integrated (enable SENTRY_DSN) |
| ⚠️ Performance metrics | **TODO** | Sentry Performance available when DSN set |

### Security Hardening (Optional)

| Task | Status | Notes |
|------|--------|-------|
| ✅ Security middleware | DONE | XSS, Content-Type nosniff, X-Frame-Options |
| ✅ HSTS configuration | DONE | 1 year HSTS when DEBUG=False |
| ✅ Content Security Policy | DONE | Basic CSP configured in settings.py |

---

## Quick Start Commands

### 1. Your SECRET_KEY (already generated)
```
yE9MDgvcSSUJSvFUp-O3SfyBrzj-97X_iFoXNFz654PhWFO8pi2dO7uclAVlcIqSnA4
```

To generate a new SECRET_KEY:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 2. Railway Environment Variables Setup
Add these in Railway Dashboard → Your App Service → Settings → Environment:

```
DEBUG=False
SECRET_KEY=yE9MDgvcSSUJSvFUp-O3SfyBrzj-97X_iFoXNFz654PhWFO8pi2dO7uclAVlcIqSnA4
ALLOWED_HOSTS=plagenor.up.railway.app
CSRF_TRUSTED_ORIGINS=https://plagenor.up.railway.app
DATABASE_URL=<your-postgresql-connection-string>
```

### 3. Test Local Production Build
```bash
# Set production environment
export DEBUG=False
export SECRET_KEY="your-generated-key"
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Test with gunicorn
gunicorn plagenor.wsgi:application --bind 0.0.0.0:8000 --workers 2
```

### 4. Railway Deployment Steps

1. **Connect Database**
   - Go to Railway Dashboard
   - Select your PostgreSQL service
   - Copy the Connection String
   - Go to your App service → Settings → Environment
   - Add `DATABASE_URL` with the connection string

2. **Configure Environment Variables**
   ```
   DEBUG=False
   SECRET_KEY=<generated-key>
   ALLOWED_HOSTS=plagenor.up.railway.app
   CSRF_TRUSTED_ORIGINS=https://plagenor.up.railway.app
   ```

3. **Deploy**
   - Railway auto-deploys on git push
   - Or use: `railway up`

4. **Verify**
   - Check logs for errors: `railway logs`
   - Test the app at your domain

---

## Pre-Deployment Verification Checklist

- [ ] `DEBUG=False` in environment
- [ ] Strong `SECRET_KEY` generated and set
- [ ] `ALLOWED_HOSTS` includes production domain
- [ ] `CSRF_TRUSTED_ORIGINS` includes production domain
- [ ] PostgreSQL `DATABASE_URL` configured
- [ ] SMTP settings configured for emails
- [ ] (Optional) Sentry DSN configured
- [ ] Database migrations run successfully
- [ ] Static files collected
- [ ] HTTPS working (automatic on Railway)
- [ ] Rate limiting active
- [ ] Test login/logout flow
- [ ] Test file upload functionality
- [ ] Verify notification emails can be sent

---

## Troubleshooting

### "DisallowedHost" Error
- Add your domain to `ALLOWED_HOSTS`
- Check for `www.` prefix variants

### CSRF Verification Failed
- Add domain to `CSRF_TRUSTED_ORIGINS` with https://

### Static Files Not Loading
- Ensure `python manage.py collectstatic` ran
- Check `STATIC_ROOT` path
- Verify WhiteNoise is in INSTALLED_APPS

### Database Connection Error
- Verify `DATABASE_URL` format: `postgresql://user:pass@host:port/db`
- Check connection credentials
- Ensure database is accessible from deployment platform

### Email Not Sending
- Verify SMTP credentials
- For Gmail: Use App Password (not regular password)
- Check SMTP_HOST and SMTP_PORT

---

## Resources

- **Django Deployment**: https://docs.djangoproject.com/en/stable/howto/deployment/
- **Railway Docs**: https://docs.railway.app/
- **Whitenoise**: http://whitenoise.evans.io/
- **Sentry Django**: https://docs.sentry.io/platforms/python/guides/django/
- **Django Storages**: https://django-storages.readthedocs.io/
