"""Contrôle d'intégrité des originaux officiels (porte G0_SOURCE).

Designed by Prof. Merzoug Mohamed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DONNEES = PROJECT / "references_officielles" / "donnees"
ORIGINAUX = PROJECT / "references_officielles" / "originaux"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    manifest = json.loads((DONNEES / "manifest_sources.json").read_text(encoding="utf-8"))
    divergent = 0
    absent = 0

    print("Contrôle d'intégrité des sources officielles (porte G0_SOURCE)\n")
    for entry in manifest["sources"]:
        name = entry["file"].split("/")[-1]
        path = ORIGINAUX / name
        if not path.is_file():
            absent += 1
            print(f"[ABSENT]     {entry['id']:<20} {name}")
            print("             → aucune règle normative dérivée ne peut être activée.")
            continue
        actual = sha256_file(path)
        if actual == entry["sha256"]:
            print(f"[CONFORME]   {entry['id']:<20} {name}")
        else:
            divergent += 1
            print(f"[DIVERGENT]  {entry['id']:<20} {name}")
            print(f"             attendu : {entry['sha256']}")
            print(f"             obtenu  : {actual}")
            print("             → toutes les règles liées doivent être suspendues.")

    print(
        f"\nBilan : {len(manifest['sources'])} source(s) — "
        f"{absent} absente(s), {divergent} divergente(s)."
    )
    if divergent:
        print("\nEMPREINTE DIVERGENTE — revalidation humaine obligatoire avant tout usage.")
        return 2
    if absent:
        print("\nSources absentes : les règles normatives restent inactives.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
