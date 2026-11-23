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
| Audit controls | `controls.csv`; NIS2 requirement IDs parsed from the control's framework sections (`Art. 21(2)(d)`, `Article 23(4)`, `IR 6.6`) |
| Audit evidence and its download URLs | evidence artifacts, linked by related control name |
| In-scope people (start and end dates) | `PO-hires`, `PO-terminations` |
| Code changes | `PO-changes` |

## Limits

- The connector does not pull the entity's scope and context. Ask the entity for its classification and jurisdiction analysis and write `context.yaml` at the engagement root.
- Vanta has no record of submissions to a CSIRT or competent authority. Ask for the incident register and the reporting records with timestamps; without them the Art. 23 units cannot pass.
- Automated test results reflect Vanta's snapshot at the time they were shared with the audit, not a history across the records period. Confirm snapshots were taken during the period, or treat the measure as audited at one point in time.
- A section that does not name the article ("21.2.d") is not recognized. Check `controls.csv` after the first pull; controls with no recognized requirement are reported by `check`.
- Not yet run against a live Vanta tenant; check the ingest warnings on first use.
