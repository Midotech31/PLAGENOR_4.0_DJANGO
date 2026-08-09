"""Configuration locale de l'application.

Application locale d'évaluation des manifestations scientifiques internationales.
Conçue par Prof. Merzoug Mohamed / Designed by Prof. Merzoug Mohamed.

Aucune configuration de compte, aucun mot de passe applicatif, aucune ressource
distante. Toutes les valeurs sont lues depuis l'environnement local ou prennent
une valeur par défaut sûre.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "Commission MSI — Assistant d'examen des manifestations scientifiques internationales"
APP_SHORT_NAME = "Commission MSI"
SIGNATURE = "Designed by Prof. Merzoug Mohamed"
SIGNATURE_FR = "Conçu par le Professeur Merzoug Mohamed"
EVALUATOR_LABEL = "Prof. Merzoug Mohamed"

UNCERTAIN_MESSAGE = (
    "Contenu illisible ou insuffisamment fiable — vérification humaine obligatoire."
)
CONTRADICTION_MESSAGE = (
    "Contradiction réglementaire détectée — interprétation humaine obligatoire."
)
DRAFT_BANNER = "Projet de rapport — validation humaine obligatoire"

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "oui"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Réglages effectifs, résolus une seule fois au démarrage."""

    version: str = field(default_factory=lambda: _read_version())
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("MSI_DATA_DIR", str(PROJECT_DIR / "data"))).resolve())
    host: str = field(default_factory=lambda: os.environ.get("MSI_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("MSI_PORT", 8731))
    allow_remote_host: bool = field(default_factory=lambda: _env_bool("MSI_ALLOW_REMOTE", False))
    max_upload_mb: int = field(default_factory=lambda: _env_int("MSI_MAX_UPLOAD_MB", 120))
    ocr_languages: str = field(default_factory=lambda: os.environ.get("MSI_OCR_LANGUAGES", "fra+ara+eng"))
    ocr_dpi: int = field(default_factory=lambda: _env_int("MSI_OCR_DPI", 300))
    ocr_low_confidence: int = field(default_factory=lambda: _env_int("MSI_OCR_LOW_CONFIDENCE", 65))
    tesseract_cmd: str = field(default_factory=lambda: os.environ.get("MSI_TESSERACT_CMD", ""))
    min_justification_length: int = field(default_factory=lambda: _env_int("MSI_MIN_JUSTIFICATION", 20))
    min_motivation_length: int = field(default_factory=lambda: _env_int("MSI_MIN_MOTIVATION", 8))
    evaluator_label: str = field(default_factory=lambda: os.environ.get("MSI_EVALUATOR", EVALUATOR_LABEL))

    # Traitement asynchrone durable (§6) ------------------------------
    worker_enabled: bool = field(default_factory=lambda: _env_bool("MSI_WORKER_ENABLED", True))

    # Mode d'intelligence artificielle (§5) ---------------------------
    #: `HYBRID_STRICT` ou `LOCAL_ONLY`. Le mode local ne fournit pas le même
    #: niveau d'analyse sémantique ni de recherche publique, et le dit.
    analysis_mode: str = field(
        default_factory=lambda: os.environ.get("ANALYSIS_MODE", "LOCAL_ONLY").upper()
    )
    #: La clé n'est jamais écrite dans le code ni dans un fichier versionné :
    #: elle vient de l'environnement ou du coffre de secrets du système.
    anthropic_api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    #: Identifiants de modèles configurables — aucun alias « latest » codé en dur.
    anthropic_model_analysis: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_MODEL_ANALYSIS", "")
    )
    anthropic_model_audit: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_MODEL_AUDIT", "")
    )
    allow_external_ai: bool = field(default_factory=lambda: _env_bool("ALLOW_EXTERNAL_AI", False))
    #: Le PDF original ne quitte jamais le poste par défaut.
    send_original_pdf: bool = field(default_factory=lambda: _env_bool("SEND_ORIGINAL_PDF", False))
    #: Les pièces d'identité ne sont jamais transmises — la valeur reste `False`
    #: quoi qu'en dise l'environnement (voir `AIProvider`).
    send_identity_documents: bool = field(
        default_factory=lambda: _env_bool("SEND_IDENTITY_DOCUMENTS", False)
    )
    web_search_enabled: bool = field(default_factory=lambda: _env_bool("WEB_SEARCH_ENABLED", False))
    web_search_max_uses: int = field(default_factory=lambda: _env_int("WEB_SEARCH_MAX_USES", 30))
    #: Le traitement externe ne démarre pas tant que la configuration de
    #: confidentialité n'a pas été validée une fois.
    privacy_acknowledged: bool = field(
        default_factory=lambda: _env_bool("MSI_PRIVACY_ACKNOWLEDGED", False)
    )

    # Modèle local (mode `LOCAL_MODEL`) -------------------------------
    #: Adresse du serveur de modèle local. Boucle locale par défaut : un
    #: modèle « local » qui écouterait sur le réseau ne le serait plus.
    local_model_url: str = field(
        default_factory=lambda: os.environ.get("MSI_LOCAL_MODEL_URL", "http://127.0.0.1:11434")
    )
    #: Identifiant exact du modèle installé (par exemple `qwen2.5:7b`). Aucun
    #: défaut : un identifiant deviné produirait une erreur incompréhensible.
    local_model_name: str = field(
        default_factory=lambda: os.environ.get("MSI_LOCAL_MODEL", "")
    )
    #: Fenêtre de contexte demandée au modèle local, en jetons. **Réglage
    #: critique** : la valeur par défaut d'Ollama (2048) tronquerait
    #: silencieusement les pages transmises, et le modèle répondrait sur un
    #: texte amputé sans que rien ne le signale.
    local_model_context: int = field(
        default_factory=lambda: _env_int("MSI_LOCAL_MODEL_CONTEXT", 8192)
    )
    #: Un modèle local sur processeur est lent : le délai est large, et c'est
    #: le travail durable qui protège de l'attente, pas un délai court.
    local_model_timeout: int = field(
        default_factory=lambda: _env_int("MSI_LOCAL_MODEL_TIMEOUT", 900)
    )

    # Chemins dérivés -------------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.data_dir / "commission_msi.sqlite3"

    @property
    def key_path(self) -> Path:
        return self.data_dir / "master.key"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def regulations_dir(self) -> Path:
        return self.data_dir / "regulations"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.db_path}"

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.documents_dir,
            self.reports_dir,
            self.regulations_dir,
            self.backups_dir,
            self.temp_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _read_version() -> str:
    version_file = PROJECT_DIR / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Retourne les réglages courants (mémorisés)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Réinitialise le cache de configuration — utilisé par les tests."""
    global _settings
    _settings = None
