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
    api_url: https://public-api.eu.drata.com   # US: https://public-api.drata.com, APAC: https://public-api.apac.drata.com
    framework_tag: NIS2                        # Drata's tag for the NIS2 framework (default; check yours in Drata)
```

## What is pulled

| Drata | Bundle |
|---|---|
| Controls and their NIS2 requirements | `controls.csv` with Drata control codes as IDs; controls mapped to no NIS2 requirement are left out |
| Evidence library, current versions | evidence artifacts, linked by control |
| Personnel (start and separation dates) | `PO-hires`, `PO-terminations` |
| Monitoring tests | one JSON export, current state only |

## Limits

- The connector does not pull the entity's scope and context. Ask the entity for its classification and jurisdiction analysis and write `context.yaml` at the engagement root.
- Drata has no record of submissions to a CSIRT or competent authority. Ask for the incident register and the reporting records with timestamps; without them the Art. 23 units cannot pass.
- Requirement names must name the article point or Annex section (`Art. 21(2)(d)`, `IR 6.6`) to be recognized; check how many controls the ingest warnings say were left out.
- Monitoring tests show the state at pull time, not a history across the records period. Do not use them alone as evidence for an audit.
- Not yet run against a live Drata account; check the ingest warnings on first use.
