"""Create welcome notifications for all existing users."""
from django.core.management.base import BaseCommand
from accounts.models import User
from notifications.models import Notification


class Command(BaseCommand):
    help = 'Create welcome notifications for all users'

    def handle(self, *args, **options):
        for u in User.objects.filter(is_active=True):
            obj, created = Notification.objects.get_or_create(
                user=u,
                message='Bienvenue sur PLAGENOR 4.0 !',
                defaults={'notification_type': 'SYSTEM'}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Created notification for {u.username}'))
            else:
                self.stdout.write(f'  Already exists for {u.username}')
        self.stdout.write(self.style.SUCCESS(f'Total: {Notification.objects.count()} notifications'))
