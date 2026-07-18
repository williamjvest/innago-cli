# innago-cli

Command-line client for Innago's sanctioned Open API, with an optional browser-session adapter for capabilities that exist only in Innago's landlord portal. It authenticates the OpenAPI with service credentials, caches and refreshes OAuth tokens, and exposes 57 sanctioned operations from Innago's live Swagger spec plus the documented health endpoint.

## Status

- Read operations verified live: properties, units, leases, tenants, invoices, invoice payments, individual payments, maintenance, and expenses.
- Write operations are mapped but must only be exercised against an approved real property-management job.
- Known Innago issue: filtered `GET /v1/payments` may return association/server errors; invoice-specific payment reads work.
- Innago's ReadMe omits live lease create/edit and application/applicant operations. The CLI includes them from `/openapi/swagger/v1/swagger.json`.
- The sanctioned OpenAPI does not expose invoice update or delete operations. The optional `portal` namespace can reach the same private endpoints used by Innago's UI.

## Install

```bash
ln -sf "$PWD/bin/innago" "$HOME/bin/innago"
```

The sanctioned OpenAPI commands have no third-party runtime dependencies. Python 3.9+ is sufficient. Portal login/capture additionally requires Microsoft's [`playwright-cli`](https://github.com/microsoft/playwright-cli); portal requests themselves remain standard-library-only.

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

## Experimental portal adapter

Innago's landlord web app exposes useful operations that are absent from its sanctioned OpenAPI. The `portal` namespace isolates these private, undocumented endpoints from the stable command surface.

### Login

No username or password is accepted or stored by this CLI. Login happens in Innago's real headed browser flow:

```bash
innago portal login
# Complete Innago/Auth0 login in the Chrome window, then:
innago portal capture
innago portal auth
```

`capture` reads only Innago's `AuthorizationToken_prod` and `APIToken_prod` cookies from that Playwright session. It does not save the browser's full storage state or unrelated Google cookies. The sanitized portal cache lives at `~/.cache/innago/portal.json` with mode `0600` and expires with Innago's browser token.

Existing Playwright storage state can also be imported. Only the two required Innago cookies are retained:

```bash
innago portal import-state ~/.playwright-auth/innago.json
```

### Private commands

```bash
innago portal invoice-get 12345678
innago portal invoice-delete 12345678 --confirm 12345678
innago portal raw GET /api/some/private/path
```

Invoice deletion mirrors Innago's own portal behavior. Bizarrely, its private endpoint uses an HTTP `GET` for the destructive action. The exact numeric invoice ID must be repeated with `--confirm`.

Private endpoints are not official, versioned, or promised stable by Innago. They may change without notice. Keep scripts on the sanctioned OpenAPI whenever it supports the required operation, and use `portal` only for the gaps.

## Write safety

Commands that create, alter, record, reject, cancel, sync, or delete data are real production operations. Do not use them as synthetic tests. Validate writes only against an actual approved job, confirm the payload against current API docs or observed portal behavior, execute once, then read the resulting resource back.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile bin/innago
```
