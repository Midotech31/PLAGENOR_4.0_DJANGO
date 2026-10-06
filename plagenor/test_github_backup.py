import json
from unittest.mock import Mock, patch

import jwt
from django.test import SimpleTestCase, TestCase

from plagenor import github_backup


def valid_claims():
    return {
        "repository": github_backup.ALLOWED_REPOSITORY,
        "repository_id": github_backup.ALLOWED_REPOSITORY_ID,
        "ref": github_backup.ALLOWED_REF,
        "workflow_ref": github_backup.ALLOWED_WORKFLOW_REF,
        "event_name": "workflow_dispatch",
        "sub": github_backup.EXPECTED_SUBJECT,
        "run_id": "12345",
        "run_attempt": "2",
    }


class GithubBackupOidcPureTests(SimpleTestCase):
    def test_bearer_token_requires_bearer_scheme(self):
        request = Mock(headers={"Authorization": "Basic abc"})
        self.assertEqual(github_backup._bearer_token(request), "")
        request.headers = {"Authorization": "Bearer  signed-token  "}
        self.assertEqual(github_backup._bearer_token(request), "signed-token")

    @patch("plagenor.github_backup.jwt.decode")
    @patch.object(github_backup._jwk_client, "get_signing_key_from_jwt")
    def test_decode_verifies_signature_issuer_and_audience(self, get_key, decode):
        get_key.return_value = Mock(key="public-key")
        decode.return_value = {"sub": "ok"}
        result = github_backup._decode_github_oidc("token")
        self.assertEqual(result, {"sub": "ok"})
        get_key.assert_called_once_with("token")
        kwargs = decode.call_args.kwargs
        self.assertEqual(kwargs["audience"], github_backup.OIDC_AUDIENCE)
        self.assertEqual(kwargs["issuer"], github_backup.OIDC_ISSUER)
        self.assertEqual(kwargs["algorithms"], ["RS256"])

    def test_authorized_claims_are_strict(self):
        claims = valid_claims()
        self.assertTrue(github_backup._authorized_claims(claims))
        claims["repository_id"] = "wrong"
        self.assertFalse(github_backup._authorized_claims(claims))

    def test_push_from_main_backup_workflow_is_authorized(self):
        claims = valid_claims()
        claims["event_name"] = "push"
        self.assertTrue(github_backup._authorized_claims(claims))

    def test_unexpected_event_is_rejected(self):
        claims = valid_claims()
        claims["event_name"] = "pull_request"
        self.assertFalse(github_backup._authorized_claims(claims))

    @patch("scripts.production_inventory_bootstrap._backup_database")
    def test_create_backup_uses_existing_encrypted_backup_implementation(self, backup):
        backup.return_value = {"status": "ok"}
        self.assertEqual(github_backup._create_backup(), {"status": "ok"})
        backup.assert_called_once_with()


class GithubBackupEndpointTests(TestCase):
    url = "/ops/github/database-backup/"

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_missing_bearer_is_rejected(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "missing_bearer")

    @patch("plagenor.github_backup._decode_github_oidc")
    def test_invalid_oidc_is_rejected(self, decode):
        decode.side_effect = jwt.InvalidTokenError("invalid")
        response = self.client.post(
            self.url, HTTP_AUTHORIZATION="Bearer invalid-token"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "invalid_oidc")

    @patch("plagenor.github_backup._decode_github_oidc")
    def test_wrong_workflow_claims_are_rejected(self, decode):
        claims = valid_claims()
        claims["workflow_ref"] = "someone/else/.github/workflows/x.yml@refs/heads/main"
        decode.return_value = claims
        response = self.client.post(
            self.url, HTTP_AUTHORIZATION="Bearer validly-signed-token"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "unauthorized_claims")

    @patch("plagenor.github_backup._create_backup")
    @patch("plagenor.github_backup._decode_github_oidc")
    def test_backup_failure_is_fail_closed(self, decode, create_backup):
        decode.return_value = valid_claims()
        create_backup.side_effect = RuntimeError("database unavailable")
        response = self.client.post(
            self.url, HTTP_AUTHORIZATION="Bearer validly-signed-token"
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "error", "code": "backup_failed"})

    @patch("plagenor.github_backup._create_backup")
    @patch("plagenor.github_backup._decode_github_oidc")
    def test_valid_github_workflow_creates_backup_and_returns_safe_evidence(
        self, decode, create_backup
    ):
        decode.return_value = valid_claims()
        create_backup.return_value = {
            "created_at": "2026-10-06T09:00:00Z",
            "backup_object": "database_backups/plagenor-test.dump.fernet",
            "ciphertext_sha256": "c" * 64,
            "plaintext_sha256": "p" * 64,
            "plaintext_bytes": 123,
            "ciphertext_bytes": 456,
            "database_name": "postgres",
            "postgres_server_version": "170006",
            "render_commit": "a" * 40,
        }
        response = self.client.post(
            self.url, HTTP_AUTHORIZATION="Bearer validly-signed-token"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["github_run_id"], "12345")
        self.assertEqual(payload["github_run_attempt"], "2")
        self.assertEqual(payload["backup_object"], "database_backups/plagenor-test.dump.fernet")
        self.assertNotIn("DATABASE_URL", json.dumps(payload))
        create_backup.assert_called_once_with()
