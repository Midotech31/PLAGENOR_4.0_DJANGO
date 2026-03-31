# Railway Deployment Crash Troubleshooting

## Common Causes of App Crashes

### 1. Missing Environment Variables (Most Common)

The app is likely crashing because required environment variables are not set in Railway.

**Must have in Railway Dashboard → Your App Service → Settings → Environment:**

```
DEBUG=False
SECRET_KEY=yE9MDgvcSSUJSvFUp-O3SfyBrzj-97X_iFoXNFz654PhWFO8pi2dO7uclAVlcIqSnA4
ALLOWED_HOSTS=plagenor.up.railway.app
CSRF_TRUSTED_ORIGINS=https://plagenor.up.railway.app
DATABASE_URL=<your-postgresql-connection-string>
```

### 2. How to Check Railway Logs

1. Go to Railway Dashboard
2. Select your app service
3. Click on "Deployments"
4. Click on the latest deployment
5. Click "View Logs" to see the error

### 3. Common Error Messages and Fixes

**Error: `django.core.exceptions.ImproperlyConfigured`**
- Missing SECRET_KEY or DATABASE_URL
- Fix: Add environment variables in Railway dashboard

**Error: `OperationalError: could not connect to server`**
- PostgreSQL database not connected
- Fix: Add DATABASE_URL pointing to your PostgreSQL service

**Error: `ModuleNotFoundError`**
- Missing Python package
- Fix: Check requirements.txt and ensure Railway builds correctly

**Error: `Permission denied`**
- File/directory write permission issue
- Fix: Ensure logs/data/media directories exist

### 4. Verify Database Connection

Test your DATABASE_URL format:
```
postgresql://postgres:[PASSWORD]@[HOST]:[PORT]/[DATABASE]
```

Example:
```
postgresql://postgres:password123@aws-0-us-east-1.pooler.supabase.com:6543/postgres
```

### 5. Quick Test Commands

Test database connection locally:
```bash
# Set environment variable
export DATABASE_URL="your-connection-string"

# Test connection
python manage.py dbshell
```

Test the app in production mode:
```bash
export DEBUG=False
export SECRET_KEY="yE9MDgvcSSUJSvFUp-O3SfyBrzj-97X_iFoXNFz654PhWFO8pi2dO7uclAVlcIqSnA4"
export ALLOWED_HOSTS="localhost"
python manage.py check --deploy
```

### 6. Railway-Specific Checks

1. **Check if PostgreSQL is linked:**
   - Railway Dashboard → PostgreSQL service → Connection String

2. **Reference PostgreSQL in App:**
   - Railway Dashboard → App Service → Settings → Environment
   - Add: `DATABASE_URL=${{ Postgres.DATABASE_URL }}`

3. **Check Build Logs:**
   - Any Python package import errors during build phase

### 7. Emergency Fix - Minimal Working Config

If all else fails, try this minimal Procfile:
```
web: gunicorn plagenor.wsgi:application --bind :$PORT --workers 1
```

And these minimal environment variables:
```
DEBUG=False
SECRET_KEY=any-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1
```

### 8. Database URL Reference

**For Railway PostgreSQL:**
```
postgresql://username:password@host:port/database
```

**For Supabase:**
```
postgresql://postgres:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
```

**For Neon:**
```
postgresql://[USER]:[PASSWORD]@ep-[LOCATION]-[ID].pool.dev:5432/[DATABASE]
```

### 9. Getting Help from Railway

If you still have issues:
1. Check Railway Status page
2. Contact Railway support with your deployment logs
3. Check Railway community Discord

### 10. Fallback: Deploy Without Database First

If you want to test the deployment without the database issue:

1. Set `DATABASE_URL` to an empty value or remove it
2. The app will fall back to SQLite (for testing only)
3. Add proper DATABASE_URL once the app starts

**Note:** SQLite should NOT be used in production!
