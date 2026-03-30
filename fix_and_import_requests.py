import os
import sys
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from core.models import Request

# Read the file with latin-1 encoding and convert to utf-8
with open('requests_export.json', 'r', encoding='latin-1') as f:
    content = f.read()

# Parse JSON
data = json.loads(content)

print(f"Importing {len(data)} requests to Supabase...")

for item in data:
    fields = item['fields']
    
    # Remove fields that might cause issues
    fields.pop('order_file', None)
    fields.pop('payment_receipt_file', None)
    fields.pop('report_file', None)
    
    try:
        Request.objects.create(**fields)
        print(f"  [OK] Imported request: {fields.get('title', 'Unknown')[:50]}")
    except Exception as e:
        print(f"  [ERROR] {e}")

print(f"\n[SUCCESS] Requests import completed!")
