import os
import sys
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
django.setup()

from django.core.management import call_command

# Read the JSON file with proper encoding
with open('plagenor_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Write it back with proper encoding
with open('plagenor_data_clean.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Data cleaned successfully!")
print(f"Total objects to import: {len(data)}")
