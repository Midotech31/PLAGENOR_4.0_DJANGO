"""Idempotently provision a superuser from environment variables.

Designed for hosts (e.g. Render free tier) where no interactive shell is
available to run ``createsuperuser``. Reads:

  * ``DJANGO_SUPERUSER_USERNAME`` (required to do anything)
  * ``DJANGO_SUPERUSER_PASSWORD`` (required)
  * ``DJANGO_SUPERUSER_EMAIL``    (optional)

Safe to run on every deploy: if the user already exists it is left
untouched unless ``--update-password`` is passed, in which case only the
password (and email) are refreshed. If the required variables are absent
the command is a no-op, so it never breaks a build.
"""
from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a SUPER_ADMIN superuser from DJANGO_SUPERUSER_* env vars (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--update-password',
            action='store_true',
            help="If the user already exists, reset its password/email from the env vars.",
        )

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()

        if not username or not password:
            self.stdout.write(
                "ensure_superuser: DJANGO_SUPERUSER_USERNAME / _PASSWORD not set — skipping."
            )
            return

        User = get_user_model()
        user = User.objects.filter(username=username).first()

        if user is None:
            User.objects.create_superuser(
                username=username, email=email, password=password,
            )
            self.stdout.write(self.style.SUCCESS(
                f"ensure_superuser: created superuser '{username}'."
            ))
            return

        # Already exists — guarantee it stays an admin.
        changed = []
        if not user.is_superuser:
            user.is_superuser = True
            changed.append('is_superuser')
        if not user.is_staff:
            user.is_staff = True
            changed.append('is_staff')
        if user.role != 'SUPER_ADMIN':
            user.role = 'SUPER_ADMIN'
            changed.append('role')

        if options['update_password']:
            user.set_password(password)
            changed.append('password')
            if email and user.email != email:
                user.email = email
                changed.append('email')

        if changed:
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f"ensure_superuser: updated '{username}' ({', '.join(changed)})."
            ))
        else:
            self.stdout.write(
                f"ensure_superuser: '{username}' already a superuser — no change."
            )
