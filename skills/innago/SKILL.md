---
name: innago
version: 1.0.0
description: Manage rental properties through the Innago CLI. Use this skill whenever the user mentions Innago, landlord records, rent invoices, tenant payments, leases, late fees, maintenance tickets, applications, rental collections, or asks to inspect/create/edit/delete Innago data. Enforces sanctioned OpenAPI first, private portal fallback only for API gaps, explicit write confirmation, post-write readback, safe browser-session auth, and known invoice-schedule traps.
license: MIT
metadata:
  capabilities: property-management.innago
  agents: anton
  scope: vv
---

# Innago

Operate Innago through the `innago` CLI. The CLI combines Innago's sanctioned
OpenAPI with an isolated, experimental `portal` namespace for operations that
exist only in the landlord web app.

**Repository and full command reference:**
https://github.com/williamjvest/innago-cli

## When to Use

- Read or change Innago properties, units, leases, tenants, invoices, payments,
  maintenance tickets, applications, or late fees.
- Reconcile rent schedules or confirm whether a tenant payment posted.
- Use Innago's landlord portal for a capability missing from the sanctioned API.
- Diagnose Innago authentication or API behavior.

Do not use this skill for personal spending analysis, QuickBooks invoicing, or
email drafting. Those have separate tools and systems of record.

## Decision tree

```text
Can the sanctioned OpenAPI perform the operation?
  |
  +-- YES -> use the normal innago command
  |          Read the result back after every write.
  |
  +-- NO  -> use innago portal only if a mapped private command exists
             invoice-get / invoice-delete / raw
             Private endpoints are brittle and browser-session authenticated.

No mapped command exists?
  |
  +-- Inspect the landlord UI with Playwright.
      Do not guess an endpoint or test a speculative write on production data.
```

The sanctioned API is the stable contract. Portal access is a fallback, not a
shortcut.

## Start every job

```bash
innago auth             # refresh sanctioned API token
innago health           # account/API sanity check
innago portal auth      # only when the task may need portal endpoints
```

If credentials are missing, follow the repo README to configure environment
variables or a secret manager. Never ask for or echo a credential in chat.

Portal session expired:

```bash
innago portal login
# Complete Innago's real login in the opened Chrome window.
innago portal capture
innago portal auth
```

The CLI stores only the two required Innago portal tokens at
`~/.cache/innago/portal.json` with mode `0600`. It never stores a login password.

## Safety contract

### Reads

Run read-only queries autonomously. Prefer `--raw` when parsing output:

```bash
innago --raw properties
innago --raw leases --property <propertyUid> --page 1
innago --raw tenants --lease <leaseUid>
innago --raw invoices --lease <leaseUid> --tenant <tenantUid>
innago --raw invoice <invoiceUid>
```

### Writes

Treat every write as production property-management work:

1. Confirm the requested property, unit, lease, tenant, invoice, amount, and date.
2. Read the current target before modifying it.
3. Execute once. Never use production writes as synthetic tests.
4. Read the result back through the sanctioned API whenever possible.
5. Report the exact IDs, dates, amounts, and resulting status.

Dedicated deletes require repeating the target ID:

```bash
innago maintenance-delete <maintenanceUid> --confirm <maintenanceUid>
innago portal invoice-delete <numericInvoiceId> --confirm <numericInvoiceId>
```

Generic non-read calls require `--confirm-write`:

```bash
innago raw POST /v1/... --json '{...}' --confirm-write
innago portal raw POST /api/... --json '{...}' --confirm-write
```

Never use `portal raw` to bypass a dedicated command's stronger confirmation.

## Usage

### Inspect a lease and its billing

```bash
innago --raw lease <leaseUid>
innago --raw tenants --lease <leaseUid>
innago --raw invoices --lease <leaseUid> --tenant <tenantUid>
```

Verify both layers:

- Lease header: type, start/end date, rent, frequency, due day.
- Actual invoices: every expected month, exact amount, due date, status.

A correct lease header does not prove the invoice schedule is correct.

### Create a rent invoice

```bash
innago invoice-create --json '{
  "tenantUid": "<tenantUid>",
  "leaseUid": "<leaseUid>",
  "amount": 1000,
  "item": "Rent",
  "dueDate": "2026-08-10T00:00:00"
}'
```

Use the item label `Rent` when the charge should participate in Innago's
rent-only late-fee rules. Read the returned `invoiceUid`, then fetch it and list
the lease's invoices to catch duplicates.

### Correct or delete an existing invoice

The sanctioned OpenAPI has no invoice update/delete operation. Use the portal
adapter only after confirming the numeric invoice ID:

```bash
innago --raw portal invoice-get <numericInvoiceId>
innago portal invoice-delete <numericInvoiceId> --confirm <numericInvoiceId>
```

Read the lease invoice list afterward. A successful HTTP response is not enough.

### Late fees

Before changing or waiving a fee, verify:

- invoice due date and remaining balance;
- grace period and fee amount;
- whether the rule targets the correct unit/property;
- whether it applies only to items labeled `Rent`;
- whether a prior waiver should prevent another automatic charge.

Late-fee rule configuration and fee waivers may require the landlord UI. Open the
login with `innago portal login`, then use `innago portal capture --keep-open` so
the named Playwright session remains available for UI work. Read the invoice back
through the sanctioned API afterward.

### Lease term or rent schedule correction

Use `lease-edit` when the sanctioned model covers the change. For forecast
schedule behavior that the API does not expose, inspect and edit through the UI,
then verify the lease and invoices through the API.

```bash
innago lease-edit --json '<EditLeaseModel>'
```

## Hard-won Innago behavior

1. **Month-to-month leases maintain a rolling future invoice window.** Deleting
   forecast invoices can immediately generate replacement invoices at the far
   end. If billing must stop on a date, correct the lease term first.
2. **Lease headers and forecast schedules can diverge.** Verify actual invoices,
   not just the displayed monthly rent.
3. **Invoice IDs come in two forms.** OpenAPI reads use UUIDs; portal pages and
   private invoice endpoints use numeric invoice IDs.
4. **Portal invoice deletion uses HTTP GET.** This is Innago's implementation,
   not a recommendation. Always use the dedicated confirmed command.
5. **Authorization is case-sensitive in Innago's implementation.** The CLI
   handles the required uppercase `Bearer`; do not recreate auth manually.
6. **Filtered payment reads can fail while invoice-specific payment reads work.**
   Prefer `innago invoice-payments <invoiceUid>` when reconciling one invoice.

## Getting OpenAPI access

Access is not self-service. Email `support@innago.com` with subject
`API Key Request` and request the Client ID, Client Secret, X-Api-Key, and current
integration guide. Store them in environment variables or a secret manager,
never in the repo or skill.

## Reporting results

Keep the response concise and concrete:

```text
Lease: Fixed Term, Jul 1 through Jan 31, $1,000 due monthly on the 10th.
Invoices: 7 total, Jul through Jan; Jul paid, 6 open.
Changes: removed invoice 12345678 and verified no replacement was generated.
```

If something regenerated or the UI and API disagree, say so immediately and stop
before making another write.

## Examples

- "Check whether August rent posted in Innago."
- "Fix the remaining invoice schedule through the end of this lease."
- "Waive this late fee, but recheck it next month if the invoice is still open."
- "Delete the duplicate invoice in Innago and verify it stays deleted."
