from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from erp.services.inventory_bootstrap import apply_inventory, summarize


class Command(BaseCommand):
    help = "Prévisualise ou applique la reprise institutionnelle de l'inventaire PLAGENOR 2026."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Appliquer réellement la reprise.")
        parser.add_argument("--actor", help="Nom d'utilisateur responsable de la reprise.")
        parser.add_argument(
            "--snapshot-date",
            help="Date technique du constat/reprise au format YYYY-MM-DD. Obligatoire avec --apply.",
        )

    def handle(self, *args, **options):
        preview = summarize()
        self.stdout.write(self.style.MIGRATE_HEADING("Inventaire PLAGENOR 2026 — aperçu"))
        for key, value in preview.items():
            self.stdout.write(f"{key}: {value}")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Aucune donnée n'a été modifiée. Utilisez --apply après contrôle."))
            return
        if not options.get("actor") or not options.get("snapshot_date"):
            raise CommandError("--actor et --snapshot-date sont obligatoires avec --apply.")
        user = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if user is None or user.role not in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
            raise CommandError("L'acteur doit être un Superadmin ou Admin Ops actif.")
        try:
            stats = apply_inventory(user, options["snapshot_date"])
        except ValueError as exc:
            raise CommandError("Date invalide; utilisez YYYY-MM-DD.") from exc
        self.stdout.write(self.style.SUCCESS("Reprise appliquée de manière idempotente."))
        for key, value in sorted(stats.items()):
            self.stdout.write(f"{key}: {value}")
