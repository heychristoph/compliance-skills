# Drata connector

Pulls a workspace through the Drata public API (v2).

## Configure

1. In Drata, create an API key with read access (Settings, API keys).
2. `export DRATA_API_KEY=...`
3. In `engagement.yaml`:

```yaml
source:
  connector: drata
  options:
    workspace_id: "<optional when the account has one workspace>"
    api_url: https://public-api.drata.com   # EU: https://public-api.eu.drata.com, APAC: https://public-api.apac.drata.com
    framework_tag: GDPR                     # Drata's tag for the GDPR framework (default); check yours in Drata
```

## What is pulled

| Drata | Bundle |
|---|---|
| Controls and their GDPR requirements | `controls.csv` with Drata control codes as IDs; provision IDs parsed from the requirement names (`Art. 30(1)`); controls mapped to no GDPR requirement are left out |
| Evidence library, current versions | evidence artifacts, linked by control |
| Personnel (start and separation dates) | `PO-hires`, `PO-terminations` |
| Monitoring tests | one JSON export, current state only |

## Limits

- The connector does not pull the processing scope and context. Ask the organization for it and write `context.yaml` at the engagement root.
- It builds no population of data subject requests, breaches or new processors. Ask for the request log, the breach register and the vendor register.
- Monitoring tests show the state at pull time, not a history across the records period. Do not use them alone as evidence for an audit of records over a period.
- Not yet run against a live Drata account; check the ingest warnings on first use.
