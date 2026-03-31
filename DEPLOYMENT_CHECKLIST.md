# PLAGENOR Deployment Checklist
## Version 4.0.0 - Production Deployment Guide

---

## 🚨 CRITICAL - Must Complete Before Going Live

### 1. Security Configuration

- [ ] **Generate New SECRET_KEY**
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(50))"
  ```
  Copy the output to your `.env` file as `SECRET_KEY=your_generated_key`

- [ ] **Set DEBUG=False**
  Edit `.env` file:
  ```
  DEBUG=False
  ```

- [ ] **Configure ALLOWED_HOSTS**
  Edit `.env` file with your production domain(s):
  ```
  ALLOWED_HOSTS=plagenor.essbo.dz,www.plagenor.essbo.dz
  ```

- [ ] **Enable HTTPS/SQL Redirect** (if behind SSL proxy)
  ```
  SECURE_SSL_REDIRECT=True
  ```

### 2. Database Configuration

- [ ] **Set Up PostgreSQL** (Recommended for Production)
  
  Choose a free PostgreSQL provider:
  - **Supabase**: https://supabase.com (recommended)
  - **Neon**: https://neon.tech
  - **Railway**: https://railway.app
  
  Update `.env`:
  ```
  DATABASE_URL=postgresql://user:password@host:5432/plagenor
  ```

- [ ] **Test Database Connection**
  ```bash
  python manage.py dbshell
  ```

- [ ] **Run Initial Database Migration**
  ```bash
  python manage.py migrate
  ```

### 3. Static & Media Files

- [ ] **Collect Static Files**
  ```bash
  python manage.py collectstatic --noinput
  ```

- [ ] **Configure Cloud Storage** (Recommended for Production)
  
  For AWS S3, update `.env`:
  ```bash
  AWS_ACCESS_KEY_ID=your_key
  AWS_SECRET_ACCESS_KEY=your_secret
  AWS_STORAGE_BUCKET_NAME=your-bucket
  AWS_S3_REGION_NAME=eu-west-1
  ```

- [ ] **Configure Media File Storage**
  
  For production, media files should NOT be stored on the local filesystem.
  Use S3, Google Cloud Storage, or similar.

### 4. Environment Configuration

- [ ] **Create Production .env File**
  ```bash
  cp .env.production .env
  ```

- [ ] **Update All Required Variables**
  - `SECRET_KEY` - Generate new, strong key
  - `DEBUG=False`
  - `ALLOWED_HOSTS` - Your domain
  - `DATABASE_URL` - PostgreSQL connection string
  - `SMTP_*` - Email credentials
  - `SENTRY_DSN` - (Optional) Error tracking

---

## 🟡 IMPORTANT - Should Complete Soon After Deployment

### 5. Error Tracking & Monitoring

- [ ] **Set Up Sentry (Free Tier Available)**
  
  1. Sign up at https://sentry.io
  2. Create a new project for PLAGENOR
  3. Get your DSN
  4. Add to `.env`:
     ```
     SENTRY_DSN=https://your-dsn@sentry.io/project-id
     ```

- [ ] **Configure Log Rotation**
  
  Logs are automatically stored in `logs/` directory with rotation.
  Ensure the `logs/` directory exists and is writable.

### 6. Backup Configuration

- [ ] **Set Up Automated Backups**
  
  Add to crontab (daily at 2 AM):
  ```bash
  0 2 * * * cd /path/to/plagenor && python scripts/backup_automated.py
  ```

- [ ] **Configure Backup Retention**
  ```bash
  export BACKUP_RETENTION=30  # days
  export BACKUP_PATH=/backups/plagenor
  ```

- [ ] **Test Backup Restore**
  ```bash
  python scripts/backup_automated.py --list
  ```

### 7. Rate Limiting & Security

- [ ] **Rate Limiting is Enabled by Default**
  
  Current limits:
  - Default: 100 requests/minute
  - Auth endpoints: 10 requests/minute
  - API endpoints: 60 requests/minute

- [ ] **Enable Brute Force Protection**
  
  Automatically enabled for login endpoints.
  Failed login attempts trigger temporary lockouts.

- [ ] **Configure CSRF Cookie Security**
  
  In production with HTTPS:
  ```python
  CSRF_COOKIE_SECURE = True
  SESSION_COOKIE_SECURE = True
  ```

### 8. Email Configuration

- [ ] **Configure SMTP for Production**
  
  Update `.env` with your SMTP settings:
  ```bash
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your-email@gmail.com
  SMTP_PASSWORD=your-app-password
  ```

- [ ] **Test Email Delivery**
  ```bash
  python manage.py shell
  >>> from django.core.mail import send_mail
  >>> send_mail('Test', 'Test email', 'from@example.com', ['to@example.com'])
  ```

---

## 🟢 RECOMMENDED - Performance & Best Practices

### 9. Performance Optimization

- [ ] **Set Up Redis Cache** (Optional but Recommended)
  ```bash
  pip install django-redis
  ```
  
  Add to `.env`:
  ```bash
  REDIS_URL=redis://localhost:6379/0
  CACHES = {
      'default': {
          'BACKEND': 'django_redis.cache.RedisCache',
          'LOCATION': os.getenv('REDIS_URL'),
      }
  }
  ```

- [ ] **Database Query Optimization**
  
  Add indexes for frequently queried fields:
  ```bash
  python manage.py migrate --fake-initial
  python manage.py showmigrations
  ```

- [ ] **Enable GUnicorn Workers**
  ```bash
  gunicorn plagenor.wsgi:application \
    --workers 3 \
    --worker-class sync \
    --timeout 120 \
    --bind 0.0.0.0:8000
  ```

### 10. Monitoring & Uptime

- [ ] **Set Up Uptime Monitoring**
  
  Free options:
  - UptimeRobot: https://uptimerobot.com
  - Uptime Kuma: https://uptime.kuma.pet (self-hosted)
  - Healthchecks.io: https://healthchecks.io

- [ ] **Create Health Check Endpoint**
  
  The endpoint `/dashboard/health/` should be monitored.

- [ ] **Set Up Performance Metrics**
  
  If using Sentry:
  ```bash
  # Performance monitoring is enabled by default
  # traces_sample_rate=0.1 (10% of transactions)
  ```

### 11. Security Hardening

- [ ] **Review ALLOWED_HOSTS**
  
  Ensure only your domain is listed, not wildcards.

- [ ] **Check CSRF_TRUSTED_ORIGINS**
  
  Add all domains that will access the application.

- [ ] **Review SecurityHeaders**
  
  The following headers are enabled:
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Strict-Transport-Security` (HSTS)
  - `Content-Security-Policy`

- [ ] **Disable Directory Browsing**
  
  Ensure `static/` and `media/` directories have no `index.html` or auto-indexing.

### 12. Pre-Deployment Checklist

- [ ] **Run Tests**
  ```bash
  python manage.py test
  ```

- [ ] **Check for Missing Migrations**
  ```bash
  python manage.py makemigrations --check
  ```

- [ ] **Verify All Environment Variables**
  ```bash
  python manage.py shell -c "from django.conf import settings; print(settings.DEBUG)"
  ```

- [ ] **Create Superuser**
  ```bash
  python manage.py createsuperuser
  ```

- [ ] **Seed Initial Data** (if needed)
  ```bash
  python manage.py seed_accounts
  python manage.py seed_services
  ```

- [ ] **Test in Browser**
  
  Verify all pages load correctly:
  - Homepage
  - Login/Logout
  - Dashboard
  - Document generation
  - Email notifications

---

## 📋 Deployment Steps Summary

### Quick Deployment (Development → Staging)

```bash
# 1. Pull latest code
git pull

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run migrations
python manage.py migrate

# 4. Collect static files
python manage.py collectstatic --noinput

# 5. Restart application
systemctl restart plagenor
# or
sudo systemctl restart gunicorn
```

### Production Deployment

```bash
# 1. Enable maintenance mode
# (Create maintenance.html in static/)

# 2. Pull latest code
git pull

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run migrations (if any)
python manage.py migrate

# 5. Collect static files
python manage.py collectstatic --noinput

# 6. Restart application
sudo systemctl restart gunicorn

# 7. Verify deployment
curl https://plagenor.essbo.dz/health/

# 8. Check logs
tail -f logs/plagenor.log
```

---

## 🔧 Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Check `DATABASE_URL` format
   - Verify PostgreSQL is running
   - Check firewall rules

2. **Static Files Not Loading**
   - Run `collectstatic`
   - Check `STATIC_ROOT` path
   - Verify web server permissions

3. **Email Not Sending**
   - Check SMTP credentials
   - Verify app password for Gmail
   - Check email server firewall

4. **500 Internal Server Error**
   - Check `DEBUG=True` temporarily
   - Review `logs/plagenor.log`
   - Verify environment variables

---

## 📞 Support

For deployment issues, check:
- `deploy_guide.md` - Detailed deployment instructions
- `plagenor/settings.py` - Configuration reference
- `logs/plagenor.log` - Application logs

---

**Last Updated**: 2026-03-30
**Version**: 4.0.0
