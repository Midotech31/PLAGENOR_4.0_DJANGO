# PLAGENOR 4.0 - Railway Dashboard Setup Steps

## Current Status: ✅ App Deployed and Running

Your app is live at: https://railway.com/project/dae0af48-53fb-42de-ae0c-2e065c69e4b9

---

## Step 1: Add PostgreSQL Database (Do This First)

1. In the Railway dashboard, look at the **left sidebar**
2. Click the **"+"** button (or "New" button)
3. Select **"Database"**
4. Select **"PostgreSQL"**
5. Wait for it to provision (green checkmark)

---

## Step 2: Set Environment Variables

1. Click on your service: **"railway add postgresql"** (the one showing "Online")
2. Click the **"Variables"** tab at the top
3. Click **"New Variable"** button
4. Add these variables one by one:

| Variable Name | Value |
|---------------|-------|
| `SECRET_KEY` | (See Step 2a below) |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `*` |

### Step 2a: Generate SECRET_KEY

In your terminal, run:
```cmd
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copy the output and paste it as the SECRET_KEY value.

---

## Step 3: Redeploy the App

After adding variables:
- Railway will auto-redeploy
- Or click the **"Deploy"** button in the top right

---

## Step 4: Run Database Migrations

1. Click on your service **"railway add postgresql"**
2. Click the **"Shell"** tab
3. Type this command and press Enter:
```bash
python manage.py migrate
```

---

## Step 5: Create Admin Superuser

Still in the **Shell** tab:
```bash
python manage.py createsuperuser
```

Enter when prompted:
- Username: (your choice)
- Email: (your email)
- Password: (your password)

---

## Step 6: View Your Live App

1. Click on your service
2. Look for the **public URL** (something like `https://plagenor-4-production.up.railway.app`)
3. Click it to open your app!

---

## Done! 🎉

Your PLAGENOR 4.0 app will be fully functional with:
- ✅ PostgreSQL database
- ✅ Admin user access
- ✅ All features ready

If you need help with any step, let me know!
