import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from accounts.models import User
from core.models import Service, Request

print("=== SQLITE DATABASE CONTENTS ===\n")

print(f"Users: {User.objects.count()}")
print(f"Services: {Service.objects.count()}")
print(f"Requests: {Request.objects.count()}")

if Request.objects.count() > 0:
    print("\n--- Sample Requests ---")
    for req in Request.objects.all()[:5]:
        print(f"  - {req.tracking_code}: {req.title}")

if User.objects.count() > 0:
    print("\n--- Users ---")
    for user in User.objects.all()[:5]:
        print(f"  - {user.username} ({user.email})")
