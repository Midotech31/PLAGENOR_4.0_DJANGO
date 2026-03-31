# How to Find Variables Section in Railway Dashboard

## Method 1: Scroll Down (Current Page)
1. On the current page showing "0 Variables"
2. **Scroll down** with your mouse/trackpad
3. Look for a section titled **"Variables"** or **"Environment Variables"**
4. You should see an empty list with a **"+"** or **"New Variable"** button

## Method 2: Use the Tabs at Top
1. Look at the **top of the page** where you see tabs
2. You should see: **"Details"**, **"Build Logs"**, **"Deploy Logs"**
3. Click on **"Details"** tab (if not already selected)
4. Scroll down to find Variables section

## Method 3: Use Left Sidebar
1. Look at the **left sidebar** (dark column on left)
2. Click on your service name: **"railway add postgresql"**
3. This will show service settings
4. Look for **"Variables"** option

## What You Should See
When you find it, you'll see:
```
Variables
0 Variables
[+] New Variable
```

## Next Action
Click **"New Variable"** or the **"+"** button, then add:
1. `SECRET_KEY` = `your-secret-key-here`
2. `DEBUG` = `False`
3. `ALLOWED_HOSTS` = `*`

---

## Generate SECRET_KEY First
In your terminal, run:
```cmd
python -c "import secrets; print(secrets.token_urlsafe(50))"
```
Copy the output and use it as your SECRET_KEY value.
