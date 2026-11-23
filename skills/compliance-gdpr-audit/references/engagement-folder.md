# The engagement folder

One folder per audit. Every step reads and writes files here, so any step can be rerun or resumed, by any agent. JSON Schemas for each file are in `scripts/engine/schemas/`.

## Contents
- Layout
- engagement.yaml
- bundle/ (written by the connector)
- context.yaml
- Units of work
- testplan.csv
- workpapers/
- findings.json, review/, report/

## Layout

```
<engagement>/
├── engagement.yaml        scope and settings (you or the user)
├── context.yaml           processing scope and context printed in the report; not a copy of the connector draft
├── bundle/                evidence, written once by `ingest`, then read-only
│   ├── manifest.json      every artifact: id, path, sha256, kind, controls, requirements, date, obtained
│   ├── controls.csv       the organization's control matrix, mapped to GDPR provisions
│   ├── context.yaml       processing scope and context inputs as pulled from the source
│   ├── populations/*.csv  data subject requests, incidents, new processors, hires, terminations ... (id, date, ...)
│   └── evidence/          files, prefixed with their artifact ID
├── testplan.csv           include, frequency, nature and population per unit (auditor)
├── workpapers/<id>.json   one per unit (auditor)
├── findings.json          graded findings and the conclusion
├── review/                coverage.md, requests.csv, rollup.md, qa.json, packet.md
└── report/                PDF, workpapers.xlsx, evidence-index.csv, report-data.json
```

There is no Statement of Applicability. Which obligations apply follows from `roles` (and `include_optional`), and Section V of the report shows the result.

## engagement.yaml

```yaml
schema_version: 1
organization: Kestrel Survey GmbH                 # legal name, as printed
scope: >-                                          # the processing in scope, in one sentence, in the report language
  The processing of personal data for the Kestrel Survey online survey platform: customer accounts, billing,
  marketing and staff as controller, and the survey responses customers collect as processor.
auditor: AI Audit                                  # always this; the model name is in signoff
audit_type: audit                                  # assessment | audit
language: en                                       # en or de: report wording and requirement text
roles: [controller, processor]                     # the organization's GDPR roles for the processing in scope
# include_optional: ["Art.40", "Art.41"]           # only when it adheres to a code of conduct or seeks certification (Art. 40 to 43)
period: {start: 2026-01-01, end: 2026-06-30}       # records period sampled (audit)
# as_of: 2026-06-30                                # assessment: date of the documentation review
source:
  connector: probo                                 # records | folder | probo | vanta | drata
  options: {organization_id: "..."}                # connector-specific, never secrets
management:                                        # the organization's representative, from the evidence
  name: Mara Lindqvist
  title: Managing Director
sampling_seed: 483920117                           # set by init; never change after sampling
signoff: null                                      # written only by `signoff --model`
```

`init` writes this file: `python scripts/gdpr.py init <dir> --org ... --scope ... --type audit --roles controller,processor --start ... --end ... --connector ...`. Secrets (API tokens) go in environment variables, never in this file.

| audit_type | What it is | Evidence |
|---|---|---|
| `assessment` | Documentation and readiness as of a date: are the records, policies and processes the Regulation requires in place? | One item per unit, the latest performance on or before `as_of` |
| `audit` | Compliance over a period: did the processes operate? | Records sampled over `period` |

Both types cover every obligation that applies to the roles; neither may leave a unit out.

**roles** decides applicability. An obligation applies when its `roles` in `assets/frameworks/gdpr.yaml` include one of the engagement's roles. A controller-only engagement drops the processor obligations (Art. 28(2), 28(3)(a), (b), (e), (g), 28(4), 30(2), 33(2)), and a processor-only engagement drops the controller obligations (Chapter III and most of Chapter II, Art. 24 to 26, 28(1), 30(1), 33(1), 33(5), 34 to 36). Art. 40 to 43 are optional and apply only when listed in `include_optional`.

## bundle/

**manifest.json** lists every artifact. The fields that matter when auditing:

| Field | Meaning |
|---|---|
| `id` | `EV-0001` for evidence and policies, `PO-<name>` for populations, `SY-...` for the control matrix and the context inputs |
| `path` | file location relative to `bundle/` |
| `kind` | `evidence`, `policy`, `population`, `controls`, `context` |
| `controls` | control IDs the source linked this artifact to (a hint, not a limit) |
| `requirements` | GDPR provision IDs the source linked this artifact to, e.g. a breach register to `Art.33(5)` (a hint, not a limit) |
| `date` | the date the artifact refers to, when the source knows it |
| `obtained` | `direct` (pulled from the system of record) or `client` (provided by the organization); direct evidence is more reliable |

**controls.csv** columns: `id, title, description, criteria, owner, frequency, nature, population, source_ref`. `criteria` is a space-separated list of provision IDs as the catalog writes them: `Art.30(1)`, `Art.32(1)(b)`, `Art.12(3)`, `Art.44`. The full list, with titles, roles and paraphrased summaries, is `assets/frameworks/gdpr.yaml` (German text in `assets/frameworks/de/gdpr.yaml`). Connectors also recognize `Art. 30(1) GDPR`, `Article 33 (2)` and `Artikel 33 Abs. 1 DSGVO`; a whole article (`Art. 32`) expands to every catalog entry under it, and a reference more specific than the catalog (`Art. 30(1)(g)`) falls back to its parent (`Art.30(1)`).

**populations/*.csv** always start with `id,date`; other columns vary by source.

## context.yaml

The organization's description of the processing in scope. `bundle/context.yaml` is what the connector pulled, usually a draft. The file the report prints is `context.yaml` at the engagement root, written for readers and approved by the organization:

```yaml
status: draft | management-approved
scope_statement: ...      # the processing in scope (required)
services: ...             # services, categories of data subjects and of personal data, special categories (required)
role: ...                 # controller, processor, joint controller, and for which processing (required)
boundaries: ...           # organizational and technical boundaries, what is out of scope (required)
sites: [{name: ..., activities: ...}]
outsourced: [{name: ..., services: ...}]   # processors and key suppliers; these names may appear in the report
changes: ...              # significant changes in the period or since the last audit
people: ...               # organization and responsibilities: management, privacy lead, DPO (roles, not names)
processes: ...            # the data protection processes (records, requests, DPIA, breaches, transfers ...)
```

`check` warns when one of the required fields is empty or when `status` is not `management-approved`. Section II prints the fields in this order, under headings from `assets/report/text/<language>.yaml`. A string becomes paragraphs, a list becomes bullets, and a list of `{name, ...}` entries becomes "name: details" bullets.

## Units of work

A unit is either a control from `controls.csv` or a `REQ-<provision>` unit. `plan` creates a `REQ-` unit for every in-scope obligation no control maps to. A `REQ-` unit is audited directly against the provision, using artifacts whose `requirements` include it, policies, the records of processing, and anything else relevant in the bundle.

## testplan.csv

`control_id, include, frequency, nature, population, sample_size, notes`. See [planning.md](planning.md).

## workpapers/<unit>.json

Created by `sample` with the `plan` block filled in and `conclusion: pending`. The auditor fills in everything else, including an optional `statement` when the control title is not the sentence the report should print. See [control-testing.md](control-testing.md) for each field and `scripts/engine/schemas/workpaper.schema.json` for the exact shape.

## findings.json, review/, report/

- `findings.json`: see [evaluating.md](evaluating.md).
- `review/qa.json`: written by `gdpr.py qa`, never by hand.
- `review/packet.md`, `report/*`: generated by `packet` and `render`.
