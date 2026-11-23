# The engagement folder

One folder per assessment. Every step reads and writes files here, so any step can be rerun or resumed, by any agent. JSON Schemas for each file are in `scripts/engine/schemas/`.

## Contents
- Layout
- engagement.yaml
- intake/ (written by capture and detect)
- bundle/ (written by ingest)
- context.yaml
- Units of work
- testplan.csv, workpapers/, findings.json, review/, report/

## Layout

```
<engagement>/
├── engagement.yaml        scope and settings (init, detect; you for management)
├── context.yaml           the application and its context, printed in Section II
├── intake/                every capture, written once: NNNN-<via>-<title>.<ext> + .meta.json
├── bundle/                evidence, written by `ingest`, then read-only
│   ├── manifest.json      every artifact: id, path, sha256, kind, controls, requirements, date, obtained, capture
│   ├── controls.csv       the organization's control matrix (empty with intake alone)
│   └── evidence/          files, prefixed with their artifact ID
├── testplan.csv           include, frequency, nature and population per unit (you)
├── workpapers/<id>.json   one per unit (you)
├── findings.json          graded findings and the conclusion (you)
├── review/                stack.yaml, evidence-plan.md, coverage.md, requests.csv, rollup.md, qa.json, packet.md
└── report/                PDF, annex-measures.md, annex-subprocessors.md, fixes.md, workpapers.xlsx, evidence-index.csv, report-data.json
```

## engagement.yaml

```yaml
schema_version: 1
organization: Fernwerk Digital GmbH                # legal name, as printed
scope: >-                                          # one sentence, in the report language
  The Kestrel Bookings web app built for Kestrel Physio, production on Supabase (EU) and Vercel.
auditor: AI Audit                                  # always this; the model name is in signoff
audit_type: assessment                             # the only type: configuration, code and documents as of a date
language: en                                       # en or de: report wording and requirement text
roles: [processor]                                 # processor (you run production) or developer (the client runs it)
as_of: 2026-11-23                                  # the assessment date: today
sources:                                           # one `source:` or several `sources:`
  - {connector: intake, options: {}}               # captures from intake/
  - {connector: records, options: {path: ../records}}   # optional: a compliance-prep records folder
repo: /Users/me/code/kestrel-bookings              # written by detect: the repository checkout
include_optional: [SEC-AC-06, DP-AI-01, DP-AI-02]  # written by detect: optional requirements the stack uses
management:                                        # the organization's representative, from the evidence
  name: Lena Brandt
  title: Managing Director
sampling_seed: 483920117                           # set by init; never change after sampling
signoff: null                                      # written only by `signoff --model`
```

`init` writes this file:

```bash
python scripts/app.py init <dir> --org "..." --scope "..." --type assessment --as-of 2026-11-23 \
  --roles processor --language en --connector intake [--connector records --option records.path=../records]
```

With several connectors, an option without a `<connector>.` prefix belongs to the first one. Secrets (API tokens) go in environment variables or the tools' own login, never in this file.

| Field | Set by | Meaning |
|---|---|---|
| `roles` | `init --roles` | `processor` or `developer`; decides which requirements apply (Section V). |
| `as_of` | `init --as-of` | The assessment date. Configuration is read as it stands on that date. |
| `source` / `sources` | `init --connector` | `intake` always; `records` when a compliance-prep records folder exists. |
| `repo` | `detect --repo` | The repository checkout. `capture --via cli` runs commands there by default. |
| `include_optional` | `detect`, or you | Optional requirement IDs that apply: SEC-AC-06 (file storage), DP-AI-01 to DP-AI-08 (AI processing). Add IDs for features detect missed; remove one only with evidence the feature is not used. |
| `management` | you | The organization's real representative and role, taken from the evidence or asked in the one message to the user. Never a placeholder. |

**Roles.** A requirement applies when its `roles` in `assets/frameworks/app.yaml` include the engagement's role. With `processor`, every requirement applies except SEC-OPS-09 (handover documentation, developer only). With `developer`, the operating requirements drop out: team access to production (SEC-AC-07), console MFA (SEC-AUTH-05), vulnerability monitoring (SEC-CODE-04), backups and restore tests (SEC-OPS-01, SEC-OPS-02), logging and alerting (SEC-OPS-03), hosting plan (SEC-OPS-07), documented TOMs (SEC-OPS-08), instructions and records (DP-INV-03, DP-INV-04), sub-processor contracts and transfers (DP-SUP-02 to DP-SUP-06), end-of-contract return and deletion from backups (DP-LIFE-04, DP-LIFE-05), incidents and breach notice (DP-INC-01, DP-INC-02), and the AI provider contracts (DP-AI-02, DP-AI-03). Optional requirements apply only when listed in `include_optional`.

## intake/

`capture` (and `detect`, for the code scan) write each piece of evidence here once: the payload plus a `.meta.json` sidecar with how it was obtained (route, MCP server and tool and arguments, or the command and exit code, time, who, requirement IDs, recipe item). Nothing in `intake/` is overwritten or deleted. The `intake` connector turns every capture into a bundle artifact. See [capture.md](capture.md) and [connectors/intake.md](connectors/intake.md).

## bundle/

**manifest.json** lists every artifact. The fields that matter when assessing:

| Field | Meaning |
|---|---|
| `id` | `EV-0001` for evidence and documents, `SY-...` for the control matrix and context inputs |
| `path` | file location relative to `bundle/` |
| `kind` | `evidence`, `policy`, `controls`, `context`, `population` |
| `requirements` | requirement IDs the capture or source linked this artifact to (a hint, not a limit) |
| `date` | the date of the capture, or of the document |
| `obtained` | the evidence tier: `direct` (a script read it: the code scan, a connector pull), `captured` (read-only MCP or CLI, call recorded), `client` (provided by the user), `inquiry` (an answer) |
| `capture` | for intake artifacts: the recorded call (server, tool, args or command, exit code, time, by) so a reviewer can repeat it |

**controls.csv**: with `intake` alone it is empty, and every requirement in scope is assessed directly as a `REQ-` unit. With `records`, it holds the organization's measures mapped to app requirement IDs.

## context.yaml

The description of the application printed in Section II. Write it at the engagement root from the code, `review/stack.yaml` and the documents, in the report language, for the client and its customers:

```yaml
status: draft | management-approved
scope_statement: ...      # the application in scope (required)
services: ...             # who uses it, the categories of data subjects and personal data, special categories (required)
role: ...                 # who runs production and processes the data for whom; processor or developer (required)
boundaries: ...           # architecture (frontend, backend, functions, AI), environments, what is out of scope (required)
sites: [{name: Supabase eu-central-1 (Frankfurt), activities: database, auth, storage}]   # hosting regions
outsourced: [{name: Supabase, services: database, authentication, storage}]              # sub-processors and key suppliers
changes: ...              # significant recent changes (a migration off the AI builder, a new region)
people: ...               # who develops and operates it (roles, not names)
processes: ...            # how changes, access, backups, incidents and data subject requests are handled
```

`check` warns when a required field is empty or `status` is not `management-approved`. Keep `status: draft` until the user confirms it. Names in `outsourced` may appear in the report and are added to the sub-processor annex.

## Units of work

A unit is either a control from `controls.csv` or a `REQ-<requirement>` unit, for example `REQ-SEC-AC-01`. `plan` creates a `REQ-` unit for every requirement in scope that no control maps to; with `intake` alone, that is every requirement.

## testplan.csv, workpapers/, findings.json, review/, report/

- `testplan.csv`: `control_id, include, frequency, nature, population, sample_size, notes`. See [planning.md](planning.md).
- `workpapers/<unit>.json`: created by `sample` with the `plan` block and `conclusion: pending`. See [control-testing.md](control-testing.md) and `scripts/engine/schemas/workpaper.schema.json`.
- `findings.json`: see [evaluating.md](evaluating.md).
- `review/stack.yaml` and `review/evidence-plan.md`: written by `detect` (always in English; they are working files). `review/qa.json`: written by `app.py qa`, never by hand. `review/packet.md`: written by `packet`.
- `report/`: written by `render`. See [reporting.md](reporting.md).
