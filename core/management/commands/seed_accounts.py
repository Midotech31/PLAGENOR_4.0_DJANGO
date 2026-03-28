"""Create test user accounts for all roles."""
from django.core.management.base import BaseCommand
from accounts.models import User, MemberProfile


class Command(BaseCommand):
    help = 'Create test accounts for all roles'

    def handle(self, *args, **options):
        accounts = [
            ('admin_ops', 'Admin', 'Ops', 'PLATFORM_ADMIN', 'Test1234!'),
            ('analyst1', 'Ahmed', 'Benali', 'MEMBER', 'Test1234!'),
            ('analyst2', 'Fatima', 'Khelifi', 'MEMBER', 'Test1234!'),
            ('finance1', 'Karim', 'Boudiaf', 'FINANCE', 'Test1234!'),
            ('student1', 'Sara', 'Mebarki', 'REQUESTER', 'Test1234!'),
            ('client1', 'Yacine', 'Hadj', 'CLIENT', 'Test1234!'),
        ]
        for username, first, last, role, pwd in accounts:
            u, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first,
                    'last_name': last,
                    'role': role,
                    'email': f'{username}@plagenor.dz',
                }
            )
            if created:
                u.set_password(pwd)
                u.save()
                if role == 'MEMBER':
                    MemberProfile.objects.get_or_create(user=u)
                self.stdout.write(self.style.SUCCESS(f'Created: {username} ({role}) — password: {pwd}'))
            else:
                self.stdout.write(f'Already exists: {username}')
