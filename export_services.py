import os
import sys
import json
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from core.models import Service

# Export services
services_data = []
for service in Service.objects.all():
    services_data.append({
        'model': 'core.service',
        'pk': str(service.pk),
        'fields': {
            'name': service.name,
            'code': service.code,
            'description': service.description,
            'channel_availability': service.channel_availability,
            'service_type': service.service_type,
            'ibtikar_price': str(service.ibtikar_price),
            'genoclab_price': str(service.genoclab_price),
            'turnaround_days': service.turnaround_days,
            'active': service.active,
            'created_at': service.created_at.isoformat() if service.created_at else datetime.now().isoformat(),
            'updated_at': service.updated_at.isoformat() if service.updated_at else datetime.now().isoformat(),
        }
    })

# Save with proper encoding
with open('services_export.json', 'w', encoding='utf-8') as f:
    json.dump(services_data, f, ensure_ascii=False, indent=2)

print(f"Exported {len(services_data)} services to services_export.json")
