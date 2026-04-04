"""
Fix analysis mode multipliers to correct values.

Updates option_pricing for analysis_mode fields from:
- Single: ×1 (unchanged)
- Duplicata: ×2 → ×1.8
- Triplicata: ×3 → ×2.6

Usage:
    python manage.py fix_analysis_multipliers
"""

from django.core.management.base import BaseCommand
from core.models import ServiceFormField


class Command(BaseCommand):
    help = 'Fix analysis mode multipliers to correct values (Duplicata=1.8, Triplicata=2.6)'

    def handle(self, *args, **options):
        # Find all fields that have analysis mode option pricing
        fields = ServiceFormField.objects.filter(
            option_pricing__isnull=False
        ).exclude(option_pricing={})

        self.stdout.write(f"Found {fields.count()} fields with option_pricing")

        # Correct multipliers
        correct_multipliers = {
            'Single': 1.0,
            'Duplicata': 1.8,
            'Triplicata': 2.6,
            # Also handle French variants if they exist
            'Simple': 1.0,
        }

        updated_count = 0

        for field in fields:
            original_pricing = field.option_pricing.copy()
            updated = False

            # Check each option in the pricing dict
            for option_name, value in list(field.option_pricing.items()):
                # Check if this is an analysis mode option
                option_lower = option_name.lower()
                if any(mode in option_lower for mode in ['single', 'duplicata', 'triplicata', 'simple']):
                    # Find the correct multiplier
                    for correct_name, multiplier in correct_multipliers.items():
                        if correct_name.lower() == option_lower:
                            if field.option_pricing[option_name] != multiplier:
                                self.stdout.write(
                                    f"  {field.service.code} / {field.name}: "
                                    f"{option_name}: {field.option_pricing[option_name]} → {multiplier}"
                                )
                                field.option_pricing[option_name] = multiplier
                                updated = True
                            break

            if updated:
                field.save(update_fields=['option_pricing'])
                updated_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated {field.service.code} / {field.name}: "
                        f"{original_pricing} → {field.option_pricing}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Updated {updated_count} fields with correct multipliers."
            )
        )

        # Show current state of all analysis mode fields
        self.stdout.write("\n--- Current Analysis Mode Pricing ---")
        for field in fields:
            for option_name, value in field.option_pricing.items():
                if any(mode in option_name.lower() for mode in ['single', 'duplicata', 'triplicata', 'simple']):
                    self.stdout.write(
                        f"{field.service.code:15} | {field.name:20} | "
                        f"{option_name:12} | ×{value}"
                    )
