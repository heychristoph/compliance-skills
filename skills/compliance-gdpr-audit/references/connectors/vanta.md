# Vanta connector

Pulls one audit through the Vanta Auditor API. Available to audit firms registered as Vanta audit partners; the firm sees only audits assigned to it.

## Configure

1. In Vanta, open the Auditor API section and create an application. Note the client ID and secret.
2. `export VANTA_CLIENT_ID=... VANTA_CLIENT_SECRET=...`
3. In `engagement.yaml`:

```yaml
source:
  connector: vanta
  options:
    audit_id: "<optional when the firm has one active audit>"
    api_url: https://api.vanta.com     # https://api.vanta-gov.com for Vanta Gov
```

The token is requested with the scopes `auditor-api.audit:read auditor-api.auditor:read`.

## What is pulled

| Vanta | Bundle |
|---|---|
| Audit controls | `controls.csv`; GDPR provision IDs parsed from the control's framework sections and domains (`Art. 32`, `Article 30(1)`) |
| Audit evidence and its download URLs | evidence artifacts, linked by related control name |
| In-scope people (start and end dates) | `PO-hires`, `PO-terminations` |
| Code changes | `PO-changes` |

## Limits

- The connector does not pull the processing scope and context. Ask the organization for it and write `context.yaml` at the engagement root.
- It builds no population of data subject requests, breaches or new processors. Ask the organization for the request log, the breach register and the vendor register; without them, the units that sample those events cannot be audited over a period.
- A section that names a whole article (`Art. 32`) maps the control to every catalog entry under it. Check `controls.csv` after the first pull and confirm each mapping against the control's description.
- Automated test results reflect Vanta's snapshot at the time they were shared with the audit, not a history across the records period. Confirm snapshots were taken during the period, or treat the control as audited at one point in time.
- Not yet run against a live Vanta tenant; check the ingest warnings on first use.
