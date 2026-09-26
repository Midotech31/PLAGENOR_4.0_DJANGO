import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from erp.services.legacy_inventory import (
    apply_inventory,
    load_manifest_gz,
    parse_inventory_sources,
    preview_inventory,
    write_manifest_gz,
)


class Command(BaseCommand):
    help = (
        "Prévisualise ou applique l'inventaire réel PLAGENOR 2026 sans doublons, "
        "avec conservation de la provenance source."
    )

    def add_arguments(self, parser):
        parser.add_argument("--xlsx", help="Chemin du classeur Inventaire PLAGENOR2026.xlsx")
        parser.add_argument("--zip", dest="zip_path", help="Chemin de l'archive des inventaires détaillés par salle")
        parser.add_argument("--from-snapshot", help="Manifeste .json.gz déjà généré")
        parser.add_argument("--snapshot", help="Écrire le manifeste canonique .json.gz à cet emplacement")
        parser.add_argument("--apply", action="store_true", help="Appliquer réellement la reprise")
        parser.add_argument("--actor", help="Nom d'utilisateur responsable de la reprise")
        parser.add_argument("--json", action="store_true", help="Afficher le rapport au format JSON")

    def handle(self, *args, **options):
        manifest = self._manifest(options)
        if options.get("snapshot"):
            path = write_manifest_gz(manifest, options["snapshot"])
            self.stdout.write(self.style.SUCCESS(f"Manifeste écrit : {path}"))

        preview = preview_inventory(manifest)
        if not options["apply"]:
            self._print("PREVIEW", preview, options["json"])
            return

        actor_name = (options.get("actor") or "").strip()
        if not actor_name:
            raise CommandError("--actor est obligatoire avec --apply.")
        user_model = get_user_model()
        try:
            actor = user_model.objects.get(username=actor_name)
        except user_model.DoesNotExist as exc:
            raise CommandError(f"Utilisateur introuvable : {actor_name}") from exc

        result = apply_inventory(actor, manifest)
        output = {"preview": preview, "apply": result}
        self._print("APPLY", output, options["json"])

    def _manifest(self, options):
        snapshot = options.get("from_snapshot")
        if snapshot:
            if options.get("xlsx") or options.get("zip_path"):
                raise CommandError("Utilisez soit --from-snapshot, soit --xlsx + --zip.")
            path = Path(snapshot)
            if not path.exists():
                raise CommandError(f"Manifeste introuvable : {path}")
            return load_manifest_gz(path)

        xlsx = options.get("xlsx")
        zip_path = options.get("zip_path")
        if not xlsx or not zip_path:
            raise CommandError("--xlsx et --zip sont requis en l'absence de --from-snapshot.")
        for label, value in (("XLSX", xlsx), ("ZIP", zip_path)):
            if not Path(value).exists():
                raise CommandError(f"{label} introuvable : {value}")
        return parse_inventory_sources(xlsx, zip_path)

    def _print(self, title, payload, as_json):
        if as_json:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            return
        self.stdout.write(self.style.MIGRATE_HEADING(f"Inventaire PLAGENOR 2026 — {title}"))
        if title == "PREVIEW":
            source = payload["source_rows"]
            self.stdout.write("Lignes source : " + ", ".join(f"{name}={count}" for name, count in source.items()))
            equipment = payload["equipment"]
            self.stdout.write(
                f"Équipements détaillés : {equipment['detailed_rows']} lignes, "
                f"{equipment['physical_assets']} unités physiques."
            )
            chemicals = payload["chemicals"]
            self.stdout.write(
                f"Produits chimiques : {chemicals['exact_positive_balances']} soldes exacts, "
                f"{chemicals['zero_balances']} soldes nuls, "
                f"{chemicals['review_balances']} à vérifier."
            )
            self.stdout.write(
                f"Consommables : {payload['consumables']['logical_rows']} lignes logiques "
                f"({payload['consumables']['continuation_rows_merged']} continuations fusionnées)."
            )
            self.stdout.write(
                f"Réactifs : {payload['reagents']['logical_rows']} lignes logiques "
                f"({payload['reagents']['continuation_rows_merged']} continuation(s) fusionnée(s))."
            )
            self.stdout.write(
                f"Équipement à vérifier : {len(equipment['review'])}; "
                f"lignes Excel de rapprochement automatique : {equipment['matched_groups']}."
            )
        else:
            self.stdout.write(json.dumps(payload["apply"], ensure_ascii=False, indent=2, default=str))
