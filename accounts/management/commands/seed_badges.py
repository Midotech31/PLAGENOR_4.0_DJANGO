from django.core.management.base import BaseCommand
from accounts.models import BadgeConfig


class Command(BaseCommand):
    help = 'Seed the database with default badge configurations'

    def handle(self, *args, **options):
        self.stdout.write('Seeding badge configurations...')
        
        created = BadgeConfig.seed_default_badges()
        
        for badge, is_new in created:
            if is_new:
                self.stdout.write(
                    self.style.SUCCESS(f'  Created: Level {badge.level} - {badge.name} ({badge.points_threshold} pts)')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'  Exists: Level {badge.level} - {badge.name} ({badge.points_threshold} pts)')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\nCompleted! {sum(1 for _, is_new in created if is_new)} new badges created.')
        )
