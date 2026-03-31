# PLAGENOR 4.0 - Complete Railway Setup (Manual Steps)

Your app is deployed but needs final configuration. Follow these steps in your terminal:

## Step 1: Login to Railway
```cmd
railway login
```
Type `Y` when asked to open browser, then complete login.

## Step 2: Link to Your Project
```cmd
railway link
```
Select your project "railway add postgresql"

## Step 3: Add PostgreSQL Database
```cmd
railway add --database postgres
```
Select "Database" → "PostgreSQL"

## Step 4: Set Environment Variables
```cmd
railway variables set SECRET_KEY="your-generated-secret-key-here"
railway variables set DEBUG="False"
railway variables set ALLOWED_HOSTS="*"
```

Generate a secret key with:
```cmd
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

## Step 5: Run Migrations
```cmd
railway run python manage.py migrate
```

## Step 6: Create Superuser
```cmd
railway run python manage.py createsuperuser
```
Enter username, email, and password when prompted.

## Step 7: View Your App
```cmd
railway open
```

---

## Your App Details

**Project URL:** https://railway.com/project/dae0af48-53fb-42de-ae0c-2e065c69e4b9

**Status:** ✅ Deployed (needs database connection)

---

## Troubleshooting

If you get "No service linked" error:
```cmd
railway service
# Select your app service
```

If you get "Unauthorized" error:
```cmd
railway login
```

---

## Alternative: Use Railway Dashboard

You can also complete setup via web interface:
1. Go to https://railway.com/project/dae0af48-53fb-42de-ae0c-2e065c69e4b9
2. Click "New" → "Database" → "PostgreSQL"
3. Click on your app service
4. Go to "Variables" tab
5. Add the environment variables manually
6. Go to "Settings" tab
7. Click "Deploy" to restart with new settings
