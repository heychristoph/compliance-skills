# The engagement folder

One folder per audit. Every step reads and writes files here, so any step can be rerun or resumed, by any agent. JSON Schemas for the engine's files are in `scripts/engine/schemas/`.

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
├── context.yaml           entity scope and context printed in the report; not a copy of the connector draft
├── bundle/                evidence, written once by `ingest`, then read-only
│   ├── manifest.json      every artifact: id, path, sha256, kind, controls, requirements, date, obtained
│   ├── controls.csv       the entity's control matrix, mapped to NIS2 requirement IDs
│   ├── context.yaml       scope and context inputs as pulled from the source (a draft, evidence only)
│   ├── populations/*.csv  incidents, significant incidents, changes, patches, vendors, hires ... (id, date, ...)
│   └── evidence/          files, prefixed with their artifact ID
├── testplan.csv           include, frequency, nature and population per unit (auditor)
├── workpapers/<id>.json   one per unit (auditor)
├── findings.json          graded findings and the conclusion
├── review/                coverage.md, requests.csv, rollup.md, qa.json, packet.md
└── report/                PDF, workpapers.xlsx, evidence-index.csv, report-data.json
```

There is no Statement of Applicability. Which requirements apply follows from `entity_types`.

## engagement.yaml

```yaml
schema_version: 1
organization: Kestrel Cloud Services GmbH         # legal name, as printed
scope: >-                                          # the services and entity in scope, as the report prints them
  The managed cloud hosting, managed service and managed security service offerings of Kestrel Cloud
  Services GmbH, operated from its Munich headquarters and two colocation data centres.
auditor: AI Audit                                  # always this; the model name is in signoff
audit_type: audit                                  # assessment | audit
language: en                                       # en or de: report wording and requirement text
entity_types: [important, digital-providers]       # essential | important, plus digital-providers
period: {start: 2026-01-01, end: 2026-06-30}       # records period sampled (audit)
# as_of: 2026-06-30                                # assessment: date of the documentation review
source:
  connector: folder                                # folder | records | probo | vanta | drata
  options: {path: export}                          # connector-specific, never secrets
management:                                        # the entity's representative, from the evidence
  name: Mara Lindqvist
  title: Managing Director
sampling_seed: 483920117                           # set by init; never change after sampling
signoff: null                                      # written only by `signoff --model`
```

Secrets (API tokens) go in environment variables, never in this file.

| audit_type | What it is | Evidence |
|---|---|---|
| `assessment` | Documentation and readiness as of a date: are the measures, governance and reporting procedures documented and in place? | One item per unit, the latest performance as of `as_of` |
| `audit` | The measures in operation over a period: were they implemented and effective, were significant incidents reported on time? | Records sampled over `period` |

Both types cover every requirement in scope; neither may leave a unit out.

| entity_types | Requirements that apply |
|---|---|
| `essential` or `important` (one of them) | Art. 3 and 26 (always), Art. 20, 21, 23, 24 and 3(4) |
| `digital-providers` (in addition) | Art. 27 and the Annex sections `IR.1.1` to `IR.13.3` of Implementing Regulation (EU) 2024/2690 |

## bundle/

**manifest.json** lists every artifact. The fields that matter when auditing:

| Field | Meaning |
|---|---|
| `id` | `EV-0001` for evidence and policies, `PO-<name>` for populations, `SY-...` for the control matrix and the context draft |
| `path` | file location relative to `bundle/` |
| `kind` | `evidence`, `policy`, `population`, `controls`, `context` |
| `controls` | control IDs the source linked this artifact to (a hint, not a limit) |
| `requirements` | NIS2 requirement IDs the source linked this artifact to, e.g. a penetration test report to `IR.6.5` (a hint, not a limit) |
| `date` | the date the artifact refers to, when the source knows it |
| `obtained` | `direct` (pulled from the system of record) or `client` (provided by the entity); direct evidence is more reliable |

**controls.csv** columns: `id, title, description, criteria, owner, frequency, nature, population, source_ref`. `criteria` is a space-separated list of requirement IDs: `Art.3`, `Art.20(1)`, `Art.21(2)(d)`, `Art.23(4)(a)`, `Art.27`, `IR.6.6`. The full list, with titles and paraphrased summaries, is `assets/frameworks/nis2.yaml` (German text in `assets/frameworks/de/nis2.yaml`).

**populations/*.csv** always start with `id,date`; other columns vary by source. For reporting, the `date` of a significant incident should be the day the entity became aware of it.

## context.yaml

The entity's description of what is audited. The connector may write a draft to `bundle/context.yaml`; it is evidence. The report prints `context.yaml` at the engagement root, which you write from the entity's documented information, or a bundle file that is already `management-approved`.

```yaml
status: draft | management-approved
scope_statement: ...      # the services, entity and sites in scope
services: ...             # the services provided, to whom, and in which member states
role: ...                 # the classification and the reason for it: sector and type (Annex I or II), size,
                          # essential or important, digital provider or not, and the member state(s) with jurisdiction
boundaries: ...           # organizational, technological, physical
sites: [{name: ..., activities: ...}]   # main establishment and other establishments or locations
outsourced: [{name: ..., services: ...}] # key suppliers and service providers (their names may be printed)
changes: ...              # significant changes since the last audit (services, size, establishments, national law)
people: ...               # size of the workforce, the management body, who reports to it on security; no names
processes: ...            # key processes: risk management, incident handling and reporting, change, supply chain
```

`check` warns when `scope_statement`, `services`, `role` or `boundaries` is empty. Section II prints every field in the order above. Name no one but `management.name`, and include no email address or phone number.

## Units of work

A unit is either a control from `controls.csv` or a `REQ-<requirement>` unit. `plan` creates a `REQ-` unit for every in-scope requirement no control maps to. A `REQ-` unit is audited directly against the requirement, using artifacts whose `requirements` include it, policies, and anything else relevant in the bundle.

## testplan.csv

`control_id, include, frequency, nature, population, sample_size, notes`. See [planning.md](planning.md).

## workpapers/<unit>.json

Created by `sample` with the `plan` block filled in and `conclusion: pending`. The auditor fills in everything else, including an optional `statement` when the control title is not the sentence the report should print. See [control-testing.md](control-testing.md) for each field and `scripts/engine/schemas/workpaper.schema.json` for the exact shape.

## findings.json, review/, report/

- `findings.json`: see [evaluating.md](evaluating.md).
- `review/qa.json`: written by `nis2.py qa`, never by hand.
- `review/packet.md`, `report/*`: generated by `packet` and `render`.
