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
    url: https://eu.probo.com          # or us.probo.com, or the self-hosted root
    organization_id: "<Probo organization GID>"
    framework_id: "<optional; defaults to the framework whose name contains GDPR, DSGVO, General Data Protection or 2016/679>"
```

## What is pulled

| Probo | Bundle |
|---|---|
| Framework controls of the GDPR framework (`Art. 5(1)(a)` ... `Art. 49(1)`) | provision IDs, from each control's section title or name; each measure inherits the provisions of the framework controls it is linked to |
| Measures | `controls.csv` rows with IDs `M-001`, `M-002`, ... (`source_ref` keeps the Probo ID) |
| Measure evidence (files and links) | evidence artifacts, `obtained: direct` for files, `client` for links. An uploaded file often has an empty MCP `url`; the connector then reads `file.downloadUrl` and the original file name from the console API |
| Documents linked to a framework control or to a measure | latest published version as a policy artifact, with `requirements` set from the framework control. The header names the approver (`Approval:`) and each signature (`Signatures:`). `not retrieved` means that call failed. It is not "none recorded" |
| People (contract start and end) | `PO-hires` and `PO-terminations` for the period |
| Third parties | `PO-vendors` (names may appear in the report) |
| Findings (major and minor nonconformities) | `PO-nonconformities`, plus the full findings register as evidence for Art. 33(5) |
| Audits and their reports | audit list and downloaded reports as evidence for Art. 24(1), Art. 28(3)(h) and Art. 32(1)(d) |
| Risks, treatment plans | JSON exports: the risk register for Art. 24(1), Art. 32(1) and Art. 32(2), treatment plans for Art. 32(1) |
| Obligations | JSON export for Art. 5(2) and Art. 24(1) |
| Assets, data | JSON exports for Art. 30(1); the data inventory also for Art. 30(2) and Art. 5(1)(c) |
| Access review campaigns and entries | one JSON file per campaign, for Art. 32(1)(b) and Art. 32(4). Each row has the account, the decision, and `decision_note` (the reason on a defer, revoke or escalate). Use that note. A counts-only summary is not the review |
| Task comments | one JSON file per measure that has comments, linked to that control. Read them. A comment that an account has no email-and-password login means there is no 2FA setting |
| Organization context | draft `context.yaml` (status `draft`): `services` from the product and customers, `boundaries` from the architecture, `people` from the team, `processes` from the processes. Evidence only. The report does not print it |

The GDPR has no Statement of Applicability; the connector does not pull one.

## Limits

- Measures carry no reliable frequency or nature for sampling; fill them in `testplan.csv`.
- Populations are linked to controls by keywords (termination, onboarding, screening, corrective action); confirm them in `testplan.csv`.
- Probo has no register of data subject requests or new processing. Ask the organization for the request log and, if breaches are not kept as findings, the breach register; ingest them with the [folder](folder.md) connector if they cannot be attached as evidence.
- Measures marked not applicable are excluded, and requested but unfulfilled evidence is skipped; both are listed as ingest warnings, which `check` repeats.
- The organization-context draft is not the description in the report. Write `context.yaml` at the engagement root for readers, with the processing in scope and the roles; the organization reviews that file and sets `status: management-approved`.
- Tested against a local mock of Probo's published MCP API (`evals/gdpr/test_probo_connector.py` in the skills repository), not yet against a live instance; check the ingest warnings on first use.
