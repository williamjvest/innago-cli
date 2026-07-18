import importlib.machinery
import importlib.util
import base64
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "innago"


def load_cli():
    loader = importlib.machinery.SourceFileLoader("innago_cli", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeResponse:
    status = 200

    def __init__(self, body=b'{"ok": true}'):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class InnagoCliTests(unittest.TestCase):
    def setUp(self):
        self.cli = load_cli()

    def test_password_grant_uses_service_credentials(self):
        credentials = {"client_id": "client", "client_secret": "secret"}
        payload = self.cli.build_token_payload(credentials)
        self.assertEqual(
            payload,
            {
                "username": "client",
                "password": "secret",
                "client_id": "client",
                "grant_type": "password",
                "client_secret": "secret",
            },
        )

    def test_environment_credentials_take_precedence(self):
        with patch.dict(os.environ, {"INNAGO_CLIENT_ID": "from-env"}, clear=False):
            self.assertEqual(self.cli.credential_get("INNAGO_CLIENT_ID"), "from-env")

    def test_optional_agent_vault_adapter_uses_configured_vault(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(json.dumps({"agent_vault": "example-vault"}))
            self.cli.CONFIG_PATH = str(config_path)
            completed = self.cli.subprocess.CompletedProcess([], 0, stdout="credential\n", stderr="")
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(self.cli.shutil, "which", return_value="/usr/local/bin/agent-vault"),
                patch.object(self.cli.subprocess, "run", return_value=completed) as run,
            ):
                self.assertEqual(self.cli.credential_get("INNAGO_CLIENT_ID"), "credential")

            self.assertEqual(run.call_args.args[0][-2:], ["--vault", "example-vault"])

    def test_refresh_grant_payload(self):
        credentials = {"client_id": "client", "client_secret": "secret"}
        payload = self.cli.build_token_payload(credentials, refresh_token="refresh")
        self.assertEqual(payload["grant_type"], "refresh_token")
        self.assertEqual(payload["refresh_token"], "refresh")

    def test_expired_refresh_token_falls_back_to_password_grant(self):
        with (
            patch.object(
                self.cli,
                "load_cache",
                return_value={"access_token": "expired", "expires_at": 0, "refresh_token": "stale"},
            ),
            patch.object(
                self.cli,
                "mint_token",
                side_effect=[self.cli.TokenRequestError("expired refresh"), {"access_token": "fresh"}],
            ) as mint_token,
        ):
            self.assertEqual(self.cli.get_token(), "fresh")

        self.assertEqual(mint_token.call_count, 2)
        self.assertTrue(mint_token.call_args_list[0].kwargs["use_refresh"])
        self.assertTrue(mint_token.call_args_list[0].kwargs["recoverable"])

    def test_api_request_uses_live_and_documented_auth_headers(self):
        captured = {}

        def fake_urlopen(request):
            captured["authorization"] = request.get_header("Authorization")
            captured["x_api_key"] = request.get_header("X-api-key")
            captured["token"] = request.get_header("Token")
            return FakeResponse()

        credentials = {"client_id": "client", "client_secret": "secret", "x_api_key": "key"}
        with (
            patch.object(self.cli, "creds", return_value=credentials),
            patch.object(self.cli, "get_token", return_value="token"),
            patch.object(self.cli.urllib.request, "urlopen", side_effect=fake_urlopen),
        ):
            result = self.cli.api_request("GET", "/v1/health")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["authorization"], "Bearer token")
        self.assertEqual(captured["x_api_key"], "key")
        self.assertEqual(captured["token"], "key")

    def test_token_cache_is_user_only(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "token.json"
            self.cli.CACHE_PATH = str(cache_path)
            self.cli.save_cache({"access_token": "token"})
            mode = stat.S_IMODE(os.stat(cache_path).st_mode)
            self.assertEqual(mode, 0o600)
            self.assertEqual(json.loads(cache_path.read_text())["access_token"], "token")

    def test_portal_state_import_extracts_only_required_tokens(self):
        expires = int(self.cli.time.time()) + 3600
        payload = base64.urlsafe_b64encode(json.dumps({"exp": expires}).encode()).decode().rstrip("=")
        access = f"header.{payload}.signature"
        state = {
            "cookies": [
                {"name": "AuthorizationToken_prod", "value": access, "domain": ".innago.com"},
                {"name": "APIToken_prod", "value": "property-owner-token", "domain": ".innago.com"},
                {"name": "SID", "value": "google-secret", "domain": ".google.com"},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            cache_path = Path(directory) / "portal.json"
            state_path.write_text(json.dumps(state))
            self.cli.PORTAL_CACHE_PATH = str(cache_path)
            result = self.cli.portal_import_state(str(state_path))

            self.assertEqual(result["access_token"], access)
            self.assertEqual(result["api_token"], "property-owner-token")
            self.assertNotIn("google-secret", cache_path.read_text())
            self.assertEqual(stat.S_IMODE(os.stat(cache_path).st_mode), 0o600)

    def test_portal_request_uses_browser_session_headers(self):
        captured = {}

        def fake_urlopen(request):
            captured["authorization"] = request.get_header("Authorization")
            captured["token"] = request.get_header("Token")
            captured["url"] = request.full_url
            return FakeResponse()

        cache = {
            "access_token": "browser-token",
            "api_token": "property-owner-token",
            "expires_at": self.cli.time.time() + 3600,
        }
        with (
            patch.object(self.cli, "load_portal_cache", return_value=cache),
            patch.object(self.cli.urllib.request, "urlopen", side_effect=fake_urlopen),
        ):
            result = self.cli.portal_request(
                "GET", "/api/Finance/Invoice_v1/GetInvoiceDetails", query={"invoiceId": 123}
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["authorization"], "Bearer browser-token")
        self.assertEqual(captured["token"], "property-owner-token")
        self.assertEqual(
            captured["url"],
            "https://api-my.innago.com/api/Finance/Invoice_v1/GetInvoiceDetails?invoiceId=123",
        )

    def test_portal_delete_requires_exact_invoice_confirmation(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["portal", "invoice-delete", "123", "--confirm", "456"])
        with (
            patch.object(self.cli, "portal_request") as request,
            self.assertRaises(SystemExit),
        ):
            args.func(args)
        request.assert_not_called()

    def test_portal_session_name_rejects_option_or_shell_characters(self):
        for session in ("bad session", "x;rm", "--help"):
            with self.subTest(session=session), self.assertRaises(SystemExit):
                self.cli.validate_portal_session_name(session)

    def test_portal_raw_cannot_bypass_invoice_delete_confirmation(self):
        parser = self.cli.build_parser()
        args = parser.parse_args([
            "portal", "raw", "GET",
            "/api/Finance/InvoiceDelete/DeleteInvoiceById?invoiceId=123",
        ])
        with (
            patch.object(self.cli, "portal_request") as request,
            self.assertRaises(SystemExit),
        ):
            args.func(args)
        request.assert_not_called()

    def test_all_documented_command_families_are_exposed(self):
        parser = self.cli.build_parser()
        help_text = parser.format_help()
        for command in (
            "properties",
            "leases",
            "lease-create",
            "lease-edit",
            "tenants",
            "invoices",
            "payments",
            "maintenance",
            "maintenance-v1",
            "expenses",
            "applications",
            "application-settings",
            "applicant-report",
            "portal",
            "record-ref-payment",
            "sync-payments",
        ):
            self.assertIn(command, help_text)

    def test_applicant_external_reference_is_supported(self):
        parser = self.cli.build_parser()
        args = parser.parse_args(["ref", "applicant", "external-id"])
        self.assertEqual(args.entity, "applicant")

    def test_lease_write_commands_require_json(self):
        parser = self.cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["lease-create"])
        args = parser.parse_args(["lease-edit", "--json", '{"leaseId":"id"}'])
        self.assertEqual(args.json, '{"leaseId":"id"}')


if __name__ == "__main__":
    unittest.main()
