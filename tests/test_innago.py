import importlib.machinery
import importlib.util
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

    def test_api_request_uses_uppercase_bearer(self):
        captured = {}

        def fake_urlopen(request):
            captured["authorization"] = request.get_header("Authorization")
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

    def test_token_cache_is_user_only(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "token.json"
            self.cli.CACHE_PATH = str(cache_path)
            self.cli.save_cache({"access_token": "token"})
            mode = stat.S_IMODE(os.stat(cache_path).st_mode)
            self.assertEqual(mode, 0o600)
            self.assertEqual(json.loads(cache_path.read_text())["access_token"], "token")

    def test_all_documented_command_families_are_exposed(self):
        parser = self.cli.build_parser()
        help_text = parser.format_help()
        for command in (
            "properties",
            "leases",
            "tenants",
            "invoices",
            "payments",
            "maintenance",
            "expenses",
            "record-ref-payment",
            "sync-payments",
        ):
            self.assertIn(command, help_text)


if __name__ == "__main__":
    unittest.main()
