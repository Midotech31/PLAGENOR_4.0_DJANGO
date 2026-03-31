# Expose Your PLAGENOR 4.0 Service to Get Public URL

I see your service shows "Unexposed service" - this means it's not publicly accessible yet.

## Step 1: Add a Public Domain

1. In Railway dashboard, click on your service "railway add postgresql"
2. Look for **"Settings"** tab at the top
3. Click **Settings**
4. Look for **"Public Networking"** or **"Domain"** section
5. Click **"Generate Domain"** or **"Add Domain"**

## Step 2: Alternative - Use CLI

In your terminal:
```cmd
railway login
railway link
railway domain
```

## Step 3: Check Variables

Make sure you have these variables set:
- `ALLOWED_HOSTS` = `*`
- `DEBUG` = `False`

## Step 4: Redeploy

After adding domain, Railway will auto-redeploy.

## Your URL Will Be:
`https://railway-add-postgresql-production.up.railway.app`

Or a similar format shown in the dashboard.

## Step 5: View Your App

Once you see a URL in the dashboard:
1. Click it
2. OR run: `railway open`

**Have you found the "Generate Domain" or "Public Networking" option?**
