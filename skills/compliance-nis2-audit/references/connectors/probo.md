# Probo connector

Pulls from [Probo](https://github.com/getprobo/probo), hosted (`us.probo.com`, `eu.probo.com`) or self-hosted. The script calls Probo's MCP API over HTTP, so the agent does not need MCP support.

## Configure

1. In Probo, give the auditor a user in the organization, and create an OAuth access token with read scopes (at least `v1:org`, `v1:control`, `v1:document`, `v1:risk`, `v1:third-party`, `v1:iam`, `v1:access-review`, `v1:audit`).
2. Set the token in the environment: `export PROBO_TOKEN=...`
3. In `engagement.yaml`:

```yaml
source:
  connector: probo
  options:
    url: https://eu.probo.com          # or the self-hosted root
    organization_id: "<Probo organization GID>"
    framework_id: "<optional; defaults to the framework whose name contains NIS2, NIS 2, NIS-2 or 2022/2555>"
```

## What is pulled

| Probo | Bundle |
|---|---|
| Framework controls of the NIS2 framework (`Art. 21(2)(d)`, `Art. 23(4)(a)`, `IR 6.6` ...) | requirements; each measure inherits the requirements of the framework controls it is linked to. A framework control's section title or name must name the article point or Annex section; bare numbers are not recognized |
| Measures | `controls.csv` rows with IDs `M-001`, `M-002`, ... (`source_ref` keeps the Probo ID) |
| Measure evidence (files and links) | evidence artifacts, `obtained: direct` for files, `client` for links. An uploaded file often has an empty MCP `url`; the connector then reads `file.downloadUrl` and the original file name from the console API |
| Documents linked to a framework control or to a measure | latest published version as a policy artifact, with `requirements` set from the framework control. The header names the approver (`Approval:`) and each signature (`Signatures:`). `not retrieved` means that call failed. It is not "none recorded" |
| People (contract start and end) | `PO-hires` and `PO-terminations` for the period |
| Third parties | `PO-vendors` and the register, linked to Art. 21(2)(d), 21(3) and IR.5.2 |
| Findings (major and minor nonconformities) | `PO-nonconformities`, plus the full findings register as evidence for Art. 21(4) and IR.3.6 |
| Audits and their reports | audit list and downloaded reports as evidence for Art. 21(2)(f), IR.2.3 and IR.7.1 |
| Risks, treatment plans | JSON exports for Art. 21(1), 21(2)(a) and IR.2.1 |
| Obligations, assets, data | JSON exports for Art. 20(1) and IR.2.2, Art. 21(2)(i) and IR.12.4, IR.12.1 |
| Access review campaigns and entries | one JSON file per campaign, linked to Art. 21(2)(i), (j), IR.11.2 and IR.11.7. Each row has the account, the decision, and `decision_note` (the reason on a defer, revoke or escalate). Use that note. A counts-only summary is not the review |
| Task comments | one JSON file per measure that has comments, linked to that control. Read them. A comment that an account has no email-and-password login means there is no 2FA setting |
| Organization context | draft `context.yaml` (status `draft`). Evidence only. The report does not print it |

## Limits

- Probo has no incident register or authority submission records. Ask the entity for the incident register with its significance classification and for the early warnings, notifications and final reports with their submission timestamps, and add them through the folder connector or as files linked to the reporting measure. Without them the Art. 23 units cannot pass.
- Measures carry no reliable frequency or nature for sampling; fill them in `testplan.csv`.
- Populations are linked to controls by keywords (termination, onboarding, screening, corrective action); confirm them in `testplan.csv` and add the significant incident, change and patch populations the entity provides.
- Measures marked not applicable are excluded, and requested but unfulfilled evidence is skipped; both are listed as ingest warnings, which `check` repeats.
- The organization-context draft is not the description in the report. Write `context.yaml` at the engagement root for readers. The entity reviews that file and sets `status: management-approved`.
- Tested against a local mock of Probo's published MCP API (`evals/nis2/test_probo_connector.py`), not yet against a live instance with a NIS2 framework; check the ingest warnings and `controls.csv` on first use.
