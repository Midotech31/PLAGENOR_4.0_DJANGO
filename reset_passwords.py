import os
import sys
import django

# Setup Django
sys.path.insert(0, 'c:/Users/hp/Desktop/App/plagenor_django/PLAGENOR_4.0_DJANGO')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
django.setup()

from accounts.models import User

users = User.objects.all()
print("\n=== All User Passwords (password = username + '123') ===\n")
for u in users:
    u.set_password(u.username + '123')
    u.save()
    print(f"  {u.username}: {u.username}123")
print("\n")
