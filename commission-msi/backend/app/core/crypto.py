"""Chiffrement local AES-256-GCM.

Toute donnée sensible (texte de page, extrait, commentaire, justification,
document original) est chiffrée avec une clé maîtresse locale et une donnée
associée (AAD) liée à l'identifiant logique de l'objet chiffré. Une AAD
incorrecte provoque un échec de déchiffrement explicite : aucun résultat
partiel n'est jamais présenté comme valide.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_SIZE = 32  # AES-256
NONCE_SIZE = 12
MAGIC = b"MSI1"


class CryptoError(RuntimeError):
    """Erreur de chiffrement ou de déchiffrement local."""


class MasterKeyError(CryptoError):
    """La clé maîtresse est absente, illisible ou invalide."""


def generate_key() -> bytes:
    return secrets.token_bytes(KEY_SIZE)


def load_or_create_master_key(path: Path) -> bytes:
    """Charge `master.key`, ou la crée si elle n'existe pas encore.

    La clé n'est jamais régénérée si le fichier existe : la perdre rend les
    données chiffrées définitivement illisibles.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raw = path.read_bytes()
        if len(raw) != KEY_SIZE:
            raise MasterKeyError(
                "master.key est invalide (taille inattendue). Restaurez une sauvegarde : "
                "sans cette clé, les données chiffrées ne peuvent pas être relues."
            )
        return raw
    key = generate_key()
    # Écriture en mode restrictif dès la création.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    return key


def encrypt(key: bytes, plaintext: bytes, aad: str) -> bytes:
    """Chiffre `plaintext` en AES-256-GCM avec `aad` comme donnée associée."""
    if len(key) != KEY_SIZE:
        raise CryptoError("Clé de chiffrement invalide.")
    nonce = secrets.token_bytes(NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad.encode("utf-8"))
    return MAGIC + nonce + ciphertext


def decrypt(key: bytes, blob: bytes, aad: str) -> bytes:
    """Déchiffre un blob produit par :func:`encrypt`.

    Lève :class:`CryptoError` si la clé, l'AAD ou le blob ne correspondent pas.
    """
    if len(key) != KEY_SIZE:
        raise CryptoError("Clé de chiffrement invalide.")
    if not blob or len(blob) < len(MAGIC) + NONCE_SIZE + 16 or blob[: len(MAGIC)] != MAGIC:
        raise CryptoError("Bloc chiffré illisible ou tronqué.")
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_SIZE]
    ciphertext = blob[len(MAGIC) + NONCE_SIZE :]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad.encode("utf-8"))
    except InvalidTag as exc:  # pragma: no cover - dépend de la clé fournie
        raise CryptoError(
            "Déchiffrement impossible : clé maîtresse ou contexte de donnée incorrect."
        ) from exc


def encrypt_text(key: bytes, text: str | None, aad: str) -> bytes | None:
    if text is None:
        return None
    return encrypt(key, text.encode("utf-8"), aad)


def decrypt_text(key: bytes, blob: bytes | None, aad: str) -> str | None:
    if blob is None:
        return None
    return decrypt(key, blob, aad).decode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def value_fingerprint(value: str | None) -> str:
    """Empreinte d'une valeur sensible, pour l'audit sans exposition en clair."""
    if value is None:
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
