"""GitHub Actions OIDC-authenticated production database backup endpoint.

No database credential is stored in GitHub. A scheduled/manual GitHub Actions
job presents a short-lived GitHub OIDC token; PLAGENOR validates its signature
and immutable repository/workflow context, then performs the encrypted backup
inside the production container where DATABASE_URL and private storage are
already configured.
"""
from __future__ import annotations

import logging

import jwt
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger("plagenor")

OIDC_ISSUER = "https://token.actions.githubusercontent.com"
OIDC_JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks"
OIDC_AUDIENCE = "plagenor-production-backup"
ALLOWED_REPOSITORY = "Midotech31/PLAGENOR_4.0_DJANGO"
ALLOWED_REPOSITORY_ID = "1194156882"
ALLOWED_REF = "refs/heads/main"
ALLOWED_WORKFLOW_REF = (
    "Midotech31/PLAGENOR_4.0_DJANGO/"
    ".github/workflows/db-backup.yml@refs/heads/main"
)
ALLOWED_EVENTS = {"schedule", "workflow_dispatch", "push"}
EXPECTED_SUBJECT = (
    "repo:Midotech31/PLAGENOR_4.0_DJANGO:ref:refs/heads/main"
)

_jwk_client = jwt.PyJWKClient(OIDC_JWKS_URL)


def _bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return ""
    return authorization[7:].strip()


def _decode_github_oidc(token):
    signing_key = _jwk_client.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience=OIDC_AUDIENCE,
        issuer=OIDC_ISSUER,
        options={
            "require": [
                "aud", "exp", "iat", "iss", "sub",
                "repository", "repository_id", "ref",
                "workflow_ref", "event_name",
            ]
        },
    )


def _authorized_claims(claims):
    return (
        claims.get("repository") == ALLOWED_REPOSITORY
        and str(claims.get("repository_id")) == ALLOWED_REPOSITORY_ID
        and claims.get("ref") == ALLOWED_REF
        and claims.get("workflow_ref") == ALLOWED_WORKFLOW_REF
        and claims.get("event_name") in ALLOWED_EVENTS
        and claims.get("sub") == EXPECTED_SUBJECT
    )


def _create_backup():
    # Lazy import prevents the operational script from participating in normal
    # application startup. The function itself never prints credentials.
    from scripts.production_inventory_bootstrap import _backup_database
    return _backup_database()


@csrf_exempt
@never_cache
@require_POST
def github_database_backup(request):
    token = _bearer_token(request)
    if not token:
        return JsonResponse({"status": "error", "code": "missing_bearer"}, status=401)

    try:
        claims = _decode_github_oidc(token)
    except (jwt.PyJWTError, ValueError):
        logger.warning("Rejected invalid GitHub OIDC token for database backup")
        return JsonResponse({"status": "error", "code": "invalid_oidc"}, status=401)

    if not _authorized_claims(claims):
        logger.warning(
            "Rejected GitHub OIDC backup claims: repository=%s ref=%s workflow=%s event=%s",
            claims.get("repository"),
            claims.get("ref"),
            claims.get("workflow_ref"),
            claims.get("event_name"),
        )
        return JsonResponse({"status": "error", "code": "unauthorized_claims"}, status=403)

    try:
        metadata = _create_backup()
    except Exception:
        logger.exception("GitHub-triggered production database backup failed")
        return JsonResponse({"status": "error", "code": "backup_failed"}, status=503)

    # Only non-secret evidence is returned. The encrypted dump remains in the
    # private Supabase-backed media storage and cannot be served via /media/.
    return JsonResponse({
        "status": "ok",
        "created_at": metadata["created_at"],
        "backup_object": metadata["backup_object"],
        "ciphertext_sha256": metadata["ciphertext_sha256"],
        "plaintext_sha256": metadata["plaintext_sha256"],
        "plaintext_bytes": metadata["plaintext_bytes"],
        "ciphertext_bytes": metadata["ciphertext_bytes"],
        "database_name": metadata["database_name"],
        "postgres_server_version": metadata["postgres_server_version"],
        "render_commit": metadata.get("render_commit", ""),
        "github_run_id": claims.get("run_id", ""),
        "github_run_attempt": claims.get("run_attempt", ""),
    })
