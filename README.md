# innago-cli

Command-line client for Innago's sanctioned Open API. It authenticates with service credentials, caches and refreshes OAuth tokens, and exposes all 43 endpoints documented at [docs.innago.com/reference](https://docs.innago.com/reference).

## Status

- Read operations verified live: properties, units, leases, tenants, invoices, invoice payments, individual payments, maintenance, and expenses.
- Write operations are mapped but must only be exercised against an approved real property-management job.
- Known Innago issue: filtered `GET /v1/payments` may return association/server errors; invoice-specific payment reads work.

## Install

```bash
ln -sf "$PWD/bin/innago" "$HOME/bin/innago"
```

The executable has no third-party runtime dependencies. Python 3.9+ is sufficient.

## Credentials

Set these environment variables:

- `INNAGO_CLIENT_ID`
- `INNAGO_CLIENT_SECRET`
- `INNAGO_X_API_KEY`

```bash
export INNAGO_CLIENT_ID="..."
export INNAGO_CLIENT_SECRET="..."
export INNAGO_X_API_KEY="..."
```

### Optional Agent Vault adapter

If [`agent-vault`](https://github.com/williamjvest/agent-vault) is installed, set `INNAGO_AGENT_VAULT` or create `~/.config/innago/config.json`:

```json
{
  "agent_vault": "your-vault-name"
}
```

Environment variables take precedence. Credentials never live in this repository. The access and refresh-token cache is stored at `~/.cache/innago/token.json` with mode `0600`.

## Authentication

Innago's integration guide uses a service-account password grant:

```text
username      = client_id
password      = client_secret
client_id     = client_id
client_secret = client_secret
grant_type    = password
```

### Critical Innago gotcha

The PDF shows `Authorization: bearer <token>`. That fails with HTTP 401 because Innago incorrectly treats the auth scheme as case-sensitive. Requests must use uppercase:

```text
Authorization: Bearer <token>
```

See [`docs/solutions/integration-issues/innago-lowercase-bearer-authorization-20260716.md`](docs/solutions/integration-issues/innago-lowercase-bearer-authorization-20260716.md).

## Usage

```bash
innago auth
innago health
innago properties
innago units <propertyUid>
innago leases --property <propertyUid> --page 1
innago tenants --lease <leaseUid>
innago invoices --lease <leaseUid> --tenant <tenantUid>
innago invoice-payments <invoiceUid>
innago maintenance --property <propertyUid> --page 1
innago expenses
```

Run `innago --help` for the full command surface.

## Write safety

Commands that create, alter, record, reject, cancel, sync, or delete data are real production operations. Do not use them as synthetic tests. Validate writes only when Will has an actual approved job, confirm the payload against current API docs, execute once, then read the resulting resource back.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/innago
```
