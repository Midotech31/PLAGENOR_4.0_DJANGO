"""Génère la matrice exigence → source → page → test.

Designed by Prof. Merzoug Mohamed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.reference_data import DONNEES_DIR  # noqa: E402
from app.services.seed import REQUIREMENT_TESTS  # noqa: E402

OUTPUT = PROJECT / "docs" / "MATRICE_TRACABILITE.md"


def main() -> int:
    requirements = json.loads((DONNEES_DIR / "exigences_sourcees.json").read_text(encoding="utf-8"))
    sources = json.loads((DONNEES_DIR / "manifest_sources.json").read_text(encoding="utf-8"))
    tests = json.loads((DONNEES_DIR / "tests_acceptation.json").read_text(encoding="utf-8"))
    source_by_id = {entry["id"]: entry for entry in sources["sources"]}

    lines = [
        "# Matrice exigence → source → page → test",
        "",
        "*Généré par `scripts/generate_matrix.py`. Designed by Prof. Merzoug Mohamed.*",
        "",
        "> Les originaux prévalent sur toute extraction, synthèse ou règle dérivée.",
        "> Une exigence reste **inactive** tant que sa source n'est pas présente, validée",
        "> et sa traduction visée par une personne habilitée.",
        "",
        "## 1. Sources officielles",
        "",
        "| Source | Autorité | Statut | Pages | SHA-256 (tronqué) |",
        "|---|---|---|---:|---|",
    ]
    for entry in sources["sources"]:
        lines.append(
            f"| `{entry['id']}` | {entry.get('authority') or '—'} | {entry['status']} | "
            f"{entry.get('pages_rendered', 0)} | `{entry['sha256'][:16]}…` |"
        )

    lines += [
        "",
        "## 2. Exigences tracées",
        "",
        "| Exigence | Libellé | Source | Pages | Statut source | Traduction | Contradiction | Tests |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for entry in requirements["requirements"]:
        source = source_by_id.get(entry["source_id"], {})
        pages = ", ".join(str(page) for page in entry.get("pages", [])) or "—"
        test_ids = REQUIREMENT_TESTS.get(entry["id"], [])
        lines.append(
            f"| `{entry['id']}` | {entry['label']} | `{entry['source_id']}` "
            f"({source.get('status', '—')}) | {pages} | {entry['source_status']} | "
            f"{entry['translation_status']} | {entry.get('conflict_id') or '—'} | "
            f"{', '.join(f'`{test}`' for test in test_ids) or '—'} |"
        )

    lines += [
        "",
        "## 3. Mise en œuvre exigée",
        "",
    ]
    for entry in requirements["requirements"]:
        lines.append(f"- **{entry['id']} — {entry['label']}** : {entry['implementation']}")

    lines += [
        "",
        "## 4. Contradictions non arbitrées",
        "",
        "| Identifiant | Sujet | Sources | Sortie imposée |",
        "|---|---|---|---|",
    ]
    for entry in requirements.get("conflicts", []):
        lines.append(
            f"| `{entry['id']}` | {entry['subject']} | {', '.join(entry['sources'])} | "
            f"`{entry['required_output']}` |"
        )

    lines += [
        "",
        "## 5. Tests d'acceptation critiques",
        "",
        f"Porte de livraison : {tests['release_gate']['critical_failures_allowed']} échec critique "
        f"et {tests['release_gate']['high_failures_allowed']} échec majeur tolérés.",
        "",
        "| Test | Catégorie | Criticité | Scénario | Résultat attendu |",
        "|---|---|---|---|---|",
    ]
    for entry in tests["tests"]:
        lines.append(
            f"| `{entry['id']}` | {entry['category']} | {entry['criticality']} | "
            f"{entry['scenario']} | {entry['expected']} |"
        )

    lines += [
        "",
        "## 6. Sources citées mais absentes",
        "",
        "Ces références sont citées par les originaux mais ne sont pas versées au kit.",
        "Elles ne peuvent produire **aucune règle obligatoire** avant versement et validation.",
        "",
    ]
    missing = json.loads((DONNEES_DIR / "sources_manquantes_a_valider.json").read_text(encoding="utf-8"))
    for item in missing["items"]:
        lines.append(f"- {item}")
    lines += ["", f"Statut imposé : `{missing['required_status']}`.", ""]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Matrice écrite : {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
