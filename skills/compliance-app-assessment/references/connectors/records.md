# Records connector

Adds a **compliance-prep records folder** to the bundle: the YAML records and documents an organization keeps in git when it has no compliance platform (policies, vendors and their DPAs, people, risks, the data inventory). Use it next to `intake` when such a folder exists; the app's own evidence still comes from `detect` and `capture`.

## Configure

```yaml
sources:
  - {connector: intake, options: {}}
  - connector: records
    options:
      path: ../records          # the records folder, relative to the engagement folder or absolute (default: records)
      framework: app            # the framework file in records/frameworks/ to read controls from (id or file stem)
```

`app.py init <dir> ... --connector intake --connector records --option records.path=<records folder> --option records.framework=<id>`

**Which framework file.** Without `framework`, the connector looks for a file in `records/frameworks/` whose name contains "App assessment" or "Application security", and fails if there is none. Most records folders only have SOC 2, ISO 27001 or GDPR frameworks. Then either add an app framework to the records folder with compliance-prep (controls whose `ref` is an app requirement ID such as `SEC-AC-01`), or name an existing framework with `framework`: its controls will not map to app requirement IDs, so they are warned about as unmapped, but the documents and registers below are still added and linked to app requirements.

## What it reads

| Records file | Bundle |
|---|---|
| `frameworks/<name>.yaml` | the organization's controls, when their `ref` names app requirement IDs (`SEC-AC-01`, `DP-SUP-03`) |
| `measures.yaml` | `controls.csv`: one control per measure, mapped to the app requirements of the framework controls that list it |
| `evidence/<measure id>/<file>` | evidence linked to that control, dated by the git commit that added the file |
| `documents.yaml`, `documents/<id>.<ext>` | policies and procedures (TOMs, incident procedure, retention schedule, DPA templates) with version, approval and signatures |
| `vendors.yaml` | the vendor register with DPA status, linked to DP-SUP-01 and DP-SUP-03 |
| `people.yaml` | the people register, and hires and terminations for team access |
| `risks.yaml` | risk register, linked to SEC-OPS-08 |
| `data.yaml`, `assets.yaml` | data inventory and asset inventory, linked to DP-INV-01 (and DP-INV-02) |
| `audits.yaml` | audits and security tests, linked to SEC-CODE-07 |
| `access-reviews.yaml` | access reviews with entries, linked to SEC-AC-07 and SEC-AUTH-05 |
| `findings.yaml` | findings register, linked to DP-INC-01 |
| git history | the records' change history |
| `system.yaml` | a draft `context.yaml` (evidence only; write your own at the engagement root) |

## Rules that matter here

- **Provenance.** Everything is `obtained: client`: the organization keeps these files. Configuration you read through MCP or CLI is stronger evidence for the same requirement; use the records for documents (TOMs, DPAs, procedures) and registers.
- **Dates.** Files carry their git commit dates. A document committed after the assessment date did not exist on that date.
- **Vendors are sub-processor evidence, not the list.** Compare `vendors.yaml` with `subprocessors` in `review/stack.yaml`: a service the code calls that is missing from the vendor register is a DP-SUP-01 or DP-SUP-02 deviation.
- **Warnings to act on.** Framework controls with no recognizable app requirement ID; measures not linked to any requirement; a records folder that is not in git.
- **Description.** The draft `context.yaml` from `system.yaml` is evidence, not report text, even when marked approved. Write `context.yaml` at the engagement root.
