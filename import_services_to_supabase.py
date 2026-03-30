import os
import sys
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from core.models import Service
from django.db import connection

# Read the exported services
with open('services_export.json', 'r', encoding='utf-8') as f:
    services_data = json.load(f)

print(f"Importing {len(services_data)} services to Supabase...")

# Delete existing services in Supabase to avoid conflicts
Service.objects.all().delete()
print("Cleared existing services in Supabase")

# Create services
for item in services_data:
    fields = item['fields']
    Service.objects.create(
        id=item['pk'],
        name=fields['name'],
        code=fields['code'],
        description=fields['description'],
        channel_availability=fields['channel_availability'],
        service_type=fields['service_type'],
        ibtikar_price=fields['ibtikar_price'],
        genoclab_price=fields['genoclab_price'],
        turnaround_days=fields['turnaround_days'],
        active=fields['active'],
    )
    print(f"  [OK] Imported: {fields['code']} - {fields['name']}")

print(f"\n[SUCCESS] Successfully imported {len(services_data)} services to Supabase!")
