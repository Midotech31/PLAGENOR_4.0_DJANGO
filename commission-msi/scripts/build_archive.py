"""Construction de l'archive de livraison.

Une archive de cette application n'est pas un `zip -r` du répertoire de
travail : ce répertoire contient une clé de chiffrement, une base de données
réelle et des documents versés. Les emporter serait une fuite, pas une
livraison.

Le script procède donc **par liste blanche** : rien n'entre dans l'archive qui
n'ait été explicitement nommé. C'est plus verbeux qu'une liste d'exclusions,
mais un oubli y produit un fichier manquant — visible, corrigible — au lieu
d'un secret exporté.

Après construction, il **rouvre l'archive** et vérifie qu'aucun chemin interdit
ne s'y est glissé. Une vérification qui lit le produit fini vaut mieux qu'une
intention exprimée dans le code qui le fabrique.

Designed by Prof. Merzoug Mohamed.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Fichiers de la racine, nommés un par un.
ROOT_FILES = (
    "README.md",
    "CHANGELOG.md",
    "VERSION",
    "MODES.txt",
    ".env.example",
    ".gitignore",
    "install_windows.bat",
    "run_windows.bat",
    "run_tests.bat",
    "reparer_ocr_arabe.bat",
    "activer_hybrid_strict.bat",
    "desactiver_lecture_semantique.bat",
    "installer_modele_local.bat",
)

#: Répertoires embarqués, avec le motif des fichiers retenus.
TREES: tuple[tuple[str, str], ...] = (
    ("backend/app", "**/*"),
    ("backend/tests", "**/*"),
    ("backend/alembic", "**/*"),
    ("backend/migrations", "**/*"),
    ("docs", "**/*.md"),
    ("rules", "**/*.json"),
    ("scripts", "**/*.py"),
    ("frontend/src", "**/*"),
    ("frontend/tests", "**/*"),
    ("frontend/public", "**/*"),
    # L'interface compilée est embarquée à dessein : elle permet de lancer
    # l'application sans Node.js, ce qui est le cas d'un poste d'évaluation.
    ("frontend/dist", "**/*"),
    # Le manifeste et les README des sources officielles, jamais les originaux
    # eux-mêmes : ils appartiennent à l'administration, pas à la livraison.
    ("references_officielles", "**/*.json"),
    ("references_officielles", "**/*.md"),
)

#: Fichiers isolés d'un répertoire par ailleurs non embarqué.
LOOSE_FILES = (
    "backend/requirements.txt",
    "backend/requirements-dev.txt",
    "backend/requirements-ocr.txt",
    "backend/alembic.ini",
    "backend/pytest.ini",
    "backend/pyproject.toml",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/tsconfig.node.json",
    "frontend/vite.config.ts",
    "frontend/index.html",
)

#: Répertoires et fichiers qui ne doivent jamais entrer, quel que soit le
#: chemin par lequel on y arriverait.
FORBIDDEN_PARTS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "data",
        "tests_private",
        "originaux",
        "backups",
    }
)

#: Motifs de noms interdits — la clé maîtresse, la base, les secrets.
FORBIDDEN_NAMES = re.compile(
    r"(master\.key|\.key$|\.sqlite3(-wal|-shm)?$|^\.env$|\.pem$|\.pfx$|\.p12$)",
    re.IGNORECASE,
)

#: Motifs de contenu qui trahiraient un secret oublié dans un fichier texte.
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)

TEXT_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".json", ".md", ".txt", ".bat", ".ini", ".toml", ".html", ".css"}
)


def is_allowed(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in FORBIDDEN_PARTS for part in relative.parts):
        return False
    if FORBIDDEN_NAMES.search(path.name):
        return False
    return path.is_file()


def collect() -> list[Path]:
    selected: set[Path] = set()

    for name in ROOT_FILES:
        candidate = ROOT / name
        if candidate.is_file():
            selected.add(candidate)

    for name in LOOSE_FILES:
        candidate = ROOT / name
        if candidate.is_file():
            selected.add(candidate)

    for directory, pattern in TREES:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for candidate in base.glob(pattern):
            if is_allowed(candidate):
                selected.add(candidate)

    return sorted(selected)


def scan_for_secrets(files: list[Path]) -> list[str]:
    """Un secret collé par mégarde dans un fichier texte doit bloquer, pas passer."""
    found: list[str] = []
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                found.append(str(path.relative_to(ROOT)))
                break
    return found


def verify(archive: Path) -> list[str]:
    """Relit l'archive produite et signale tout chemin interdit."""
    problems: list[str] = []
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            parts = Path(name).parts[1:]  # le premier segment est le dossier racine
            if any(part in FORBIDDEN_PARTS for part in parts):
                problems.append(name)
            elif FORBIDDEN_NAMES.search(Path(name).name):
                problems.append(name)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive de livraison Commission MSI")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    stem = f"Commission_MSI_v{version}"
    target = args.output or (ROOT.parent / f"{stem}.zip")

    files = collect()
    if not files:
        print("ERREUR : aucun fichier sélectionné.", file=sys.stderr)
        return 1

    leaked = scan_for_secrets(files)
    if leaked:
        print("REFUS : un secret apparaît dans les fichiers suivants :", file=sys.stderr)
        for name in leaked:
            print(f"  - {name}", file=sys.stderr)
        return 2

    if (ROOT / "frontend" / "dist" / "index.html").is_file() is False:
        print(
            "AVERTISSEMENT : l'interface compilée est absente de l'archive. "
            "Le poste de destination devra disposer de Node.js. "
            "Exécutez « npm run build » dans frontend/ avant de reconstruire.",
            file=sys.stderr,
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            bundle.write(path, arcname=str(Path(stem) / path.relative_to(ROOT)))

    problems = verify(target)
    if problems:
        target.unlink(missing_ok=True)
        print("REFUS : l'archive contenait des chemins interdits :", file=sys.stderr)
        for name in problems:
            print(f"  - {name}", file=sys.stderr)
        return 3

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    size = target.stat().st_size
    print(f"Archive   : {target}")
    print(f"Fichiers  : {len(files)}")
    print(f"Taille    : {size / 1024 / 1024:.1f} Mo")
    print(f"SHA-256   : {digest}")
    print("Vérifié   : ni clé, ni base, ni document versé, ni secret.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
