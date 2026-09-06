"""Send one production SMTP probe and fail unless delivery is accepted."""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = (
        'Send a non-sensitive SMTP probe to SMTP_SMOKE_RECIPIENT and fail '
        'unless the configured backend accepts exactly one message.'
    )

    def handle(self, *args, **options):
        smtp_backend = 'django.core.mail.backends.smtp.EmailBackend'
        if settings.EMAIL_BACKEND != smtp_backend:
            raise CommandError('SMTP email backend is not active.')

        recipient = getattr(settings, 'SMTP_SMOKE_RECIPIENT', '').strip()
        if not recipient:
            raise CommandError('SMTP_SMOKE_RECIPIENT must be configured.')

        timestamp = timezone.now().isoformat(timespec='seconds')
        try:
            delivered = send_mail(
                subject='[PLAGENOR] SMTP delivery verification',
                message=(
                    'PLAGENOR successfully submitted this operational '
                    f'verification message at {timestamp}. No user or '
                    'request data is included.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f'SMTP delivery verification failed: {exc}') from exc

        if delivered != 1:
            raise CommandError(
                f'SMTP backend accepted {delivered!r} messages; expected 1.'
            )
        self.stdout.write(self.style.SUCCESS('SMTP delivery verification accepted.'))
