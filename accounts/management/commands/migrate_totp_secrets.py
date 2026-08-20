from django.core.management.base import BaseCommand

from accounts.models import User
from accounts.totp import PREFIX, encrypt_secret


class Command(BaseCommand):
    help = "Encrypt legacy plaintext TOTP seeds in place (idempotent)."

    def handle(self, *args, **options):
        migrated = 0
        for user in User.objects.exclude(totp_secret='').iterator():
            if user.totp_secret.startswith(PREFIX):
                continue
            user.totp_secret = encrypt_secret(user.totp_secret)
            user.save(update_fields=['totp_secret'])
            migrated += 1
        self.stdout.write(self.style.SUCCESS(
            f"Encrypted {migrated} TOTP seed(s)."))
