import os
import sys
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagenor.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

django.setup()

from accounts.models import User

users_data = []
for user in User.objects.all():
    users_data.append({
        'model': 'accounts.user',
        'pk': str(user.pk),
        'fields': {
            'password': user.password,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'is_superuser': user.is_superuser,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_active': user.is_active,
            'date_joined': user.date_joined.isoformat() if user.date_joined else None,
            'role': user.role,
            'phone': user.phone,
            'organization': user.organization,
            'ibtikar_id': user.ibtikar_id,
            'must_change_password': user.must_change_password,
            'student_level': user.student_level,
            'supervisor': user.supervisor,
            'laboratory': user.laboratory,
            'login_attempts': user.login_attempts,
        }
    })

with open('users_export.json', 'w', encoding='utf-8') as f:
    json.dump(users_data, f, ensure_ascii=False, indent=2)

print(f"Exported {len(users_data)} users to users_export.json")
