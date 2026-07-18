---
module: Innago Open API
date: 2026-07-16
problem_type: integration_issue
component: tooling
symptoms:
  - 'Documented data endpoints returned HTTP 401 with "Unauthorized Access"'
  - '/v1/health returned HTTP 200 using the same token'
  - 'JWT contained a valid PropertyOwnerId and openApiScope'
root_cause: inadequate_documentation
resolution_type: code_fix
severity: high
tags: [innago, oauth, bearer-token, case-sensitive, api-integration]
---

# Troubleshooting: Innago data endpoints reject lowercase bearer scheme

## Problem

Innago's service credentials minted a complete OpenAPI token, but every documented data endpoint returned HTTP 401 `Unauthorized Access`. The health endpoint returned HTTP 200, making the failure look like missing account or endpoint permissions.

## Environment

- Module: Innago Open API
- Affected component: `bin/innago`
- Host: macOS (Asmond)
- Date: 2026-07-16

## Symptoms

- `GET /openapi/v1/health` returned HTTP 200.
- `GET /openapi/v1/properties` returned HTTP 401 with `{"errorMessage":"Unauthorized Access"}`.
- The JWT carried `PropertyOwnerId`, `OrganizationId`, `openApiScope`, and `TwoFactorRequired=false`.
- Reissuing credentials did not appear to fix data access.

## What Didn't Work

**Using a personal Innago account email/password:**
- Triggered the user-account 2FA flow and produced partial tokens. The PDF documents a service-account flow, not a user-login flow.

**Testing account provisioning, endpoint enablement, API-key variants, and Auth0 tokens:**
- These investigations did not change the 401 because the actual failure was the authentication-scheme casing.

**Copying the PDF literally:**
- The PDF shows `Authorization: bearer <auth Token>` with lowercase `bearer`. Innago's server incorrectly treats this scheme as case-sensitive.

## Solution

Use the replacement service credentials exactly as documented for token minting, but send uppercase `Bearer` on API calls.

```python
# Before: returns 401 on data endpoints
req.add_header("Authorization", f"bearer {token}")

# After: returns account data
req.add_header("Authorization", f"Bearer {token}")
```

Token request:

```text
username      = client_id
password      = client_secret
client_id     = client_id
client_secret = client_secret
grant_type    = password
```

## Why This Works

OAuth authentication schemes are case-insensitive by specification, but Innago's OpenAPI middleware compares the scheme case-sensitively. The lowercase value copied from Innago's PDF is rejected by data authorization middleware. Uppercase `Bearer` is accepted and immediately returned live property, unit, lease, tenant, invoice, payment, maintenance, and expense data.

## Prevention

- Always honor the `token_type` returned by the token endpoint instead of normalizing it to lowercase.
- Treat HTTP 200 health plus HTTP 401 data as a possible middleware-path difference, not proof of missing account access.
- Compare request variants byte-for-byte before escalating provisioning theories.
- Keep a read-only smoke test for `innago properties` after auth changes.

## Related Issues

No related issues documented yet.
