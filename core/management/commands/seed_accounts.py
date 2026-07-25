"""Create or refresh demo user accounts for every role.

Idempotent: rerunning resets passwords + role flags on existing users,
so an operator who tweaked these locally can always restore a known
state with one command. Designed for local dev / screenshots / smoke
tests — never run this against a production DB (the passwords are
intentionally weak and well-known).

Usage:
  python manage.py seed_accounts            # creates / refreshes all roles
  python manage.py seed_accounts --quiet    # no per-row output

After running, log in at /accounts/login/ as any of the printed users
to exercise the matching role's dashboard.
"""
from django.core.management.base import BaseCommand
from accounts.models import User, MemberProfile


# (username, first_name, last_name, role, password, email, extra_fields)
DEMO_ACCOUNTS = [
    ('admin',     'Super',  'Admin',     'SUPER_ADMIN',    'admin1234',    'admin@plagenor.dz',      {'is_staff': True, 'is_superuser': True}),
    ('admin_ops', 'Karim',  'Bensaad',   'PLATFORM_ADMIN', 'platform1234', 'admin_ops@plagenor.dz',  {}),
    ('analyst',   'Ahmed',  'Benali',    'MEMBER',         'analyst1234',  'analyst@plagenor.dz',    {}),
    ('finance',   'Yacine', 'Hadj',      'FINANCE',        'finance1234',  'finance@plagenor.dz',    {}),
    ('amina',     'Amina',  'Bensalem',  'REQUESTER',      'demo1234',     'amina@plagenor.dz',      {
        'organization': 'USTO', 'laboratory': 'LABBIOMIC', 'supervisor': 'Pr. Khaldi',
        'student_level': 'doctorat', 'phone': '0555 87 65 43', 'ibtikar_id': 'IDGRSTD78901',
    }),
    ('client',    'Sami',   'Belkacem',  'CLIENT',         'client1234',   'client@plagenor.dz',     {
        'organization': 'Biopharma SPA', 'phone': '0666 11 22 33',
    }),
]


class Command(BaseCommand):
    help = 'Create or refresh demo user accounts (one per role).'

    def add_arguments(self, parser):
        parser.add_argument('--quiet', action='store_true', help='Suppress per-row output.')

    def handle(self, *args, **options):
        quiet = options.get('quiet', False)
        created_n = updated_n = 0

        for username, first, last, role, pwd, email, extras in DEMO_ACCOUNTS:
            user, was_created = User.objects.get_or_create(username=username, defaults={'email': email})

            # Always (re)set the canonical demo state so reruns repair drifted
            # rows — easier for an operator than tracking each manual edit.
            user.email = email
            user.first_name = first
            user.last_name = last
            user.role = role
            user.is_active = True
            for k, v in extras.items():
                setattr(user, k, v)
            user.set_password(pwd)
            user.save()

            if role == 'MEMBER':
                MemberProfile.objects.get_or_create(user=user)

            if was_created:
                created_n += 1
                if not quiet:
                    self.stdout.write(self.style.SUCCESS(f'  Created  {username:12s} role={role}'))
            else:
                updated_n += 1
                if not quiet:
                    self.stdout.write(f'  Refreshed {username:12s} role={role}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Done — {created_n} created, {updated_n} refreshed. '
            f'All passwords are documented in the seed_accounts command.'
        ))
        self.stdout.write('')
        self.stdout.write('Login credentials (for local development only):')
        self.stdout.write('  username        password         role              path after login')
        self.stdout.write('  ' + '-' * 84)
        for username, _, _, role, pwd, _, _ in DEMO_ACCOUNTS:
            path = {
                'SUPER_ADMIN':    '/dashboard/home/',
                'PLATFORM_ADMIN': '/dashboard/ops/',
                'MEMBER':         '/dashboard/analyst/',
                'FINANCE':        '/dashboard/finance/',
                'REQUESTER':      '/dashboard/requester/',
                'CLIENT':         '/dashboard/client/',
            }[role]
            self.stdout.write(f'  {username:15s} {pwd:16s} {role:17s} {path}')
