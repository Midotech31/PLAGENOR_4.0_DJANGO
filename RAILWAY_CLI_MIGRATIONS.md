# Run Migrations Using Railway CLI

Since the Shell tab is not visible in your dashboard, use the CLI method:

## Step 1: Open Your Terminal
Press `Win + R`, type `cmd`, press Enter

## Step 2: Navigate to Project
```cmd
cd c:\Users\hp\Desktop\App\plagenor_django\PLAGENOR_4.0_DJANGO
```

## Step 3: Login to Railway
```cmd
railway login
```
Type `Y` and complete login in browser

## Step 4: Link to Your Project
```cmd
railway link
```
Select your project

## Step 5: Run Migrations
```cmd
railway run python manage.py migrate
```

## Step 6: Create Superuser
```cmd
railway run python manage.py createsuperuser
```
Enter username, email, and password when prompted

## Step 7: Open Your App
```cmd
railway open
```

---

## Alternative: Dashboard Method

If you want to use the dashboard instead:
1. Look for a **terminal icon** in the left sidebar
2. OR check if there's a **"Console"** or **"Shell"** option in the **Settings** tab
3. OR look for three dots (⋮) menu on your deployment
