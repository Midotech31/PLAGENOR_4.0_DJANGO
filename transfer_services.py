import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from core.models import Service

# Check what services exist in current database
services = Service.objects.all()
print(f"Found {services.count()} services in current database:")
for s in services:
    print(f"  - {s.name} ({s.code})")
