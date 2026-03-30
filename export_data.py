import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

django.setup()

from django.core.management import call_command

with open('plagenor_data.json', 'w', encoding='utf-8') as f:
    call_command('dumpdata', 
                 '--exclude', 'contenttypes',
                 '--exclude', 'auth.permission', 
                 '--exclude', 'admin.logentry',
                 '--exclude', 'sessions.session',
                 '--indent', '2',
                 stdout=f)

print("Export completed successfully!")
