# Records connector

Builds the bundle from a **compliance-prep records folder**: the YAML records and evidence files a company keeps in git when it has no compliance platform. Use it when the compliance-prep skill runs with `platform: folder`.

## Configure

```yaml
source:
  connector: records
  options:
    path: ../records      # the records folder, relative to the engagement folder or absolute (default: records)
    framework: gdpr       # optional: framework id or file stem in frameworks/
```

`gdpr.py init <dir> ... --connector records --option path=<records folder>`

## What it reads

| Records file | Bundle |
|---|---|
| `frameworks/<name>.yaml` | the audited framework. Each control's `ref` becomes provision IDs: the exact catalog ID (`Art.30(1)`), or any recognized spelling (`Art. 30(1)`, `Article 33(2)`); a whole article (`Art. 32`) expands to every catalog entry under it. When the `ref` is not recognized, the control's `name` is tried. There is no Statement of Applicability for the GDPR: `applicable` and `justification` are not read |
| `measures.yaml` | `controls.csv`: one control per measure, mapped to the provisions of the framework controls that list it; the description ends with the measure's state |
| `evidence/<measure id>/<file>` | evidence linked to that control and its provisions, dated by the git commit that added the file |
| `documents.yaml`, `documents/<id>.<ext>` | policies: version, publication, approval and signatures, plus the text when the file is Markdown or text (other formats are attached as files). Provisions come from the framework controls that list the document, controls from the measures that list it |
| `people.yaml` (`contract_start`, `contract_end`) | `hires` and `terminations` populations for the period, and a people register export |
| `vendors.yaml` (`added_at`) | `vendors` population (dated by `added_at`, or the first commit of the file) and the vendor register with DPA status, linked to Art. 28(1), Art. 28(3) and Art. 44 |
| `findings.yaml` (`identified_on`) | `nonconformities` population (findings whose kind is a nonconformity) and the findings register, linked to Art. 33(5) |
| `risks.yaml` | risk register, linked to Art. 24(1), Art. 32(1) and Art. 32(2) |
| `assets.yaml` | asset inventory, linked to Art. 30(1) |
| `data.yaml` | data inventory, linked to Art. 30(1), Art. 30(2) and Art. 5(1)(c) |
| `audits.yaml` | audits recorded, linked to Art. 24(1), Art. 28(3)(h) and Art. 32(1)(d) |
| `access-reviews.yaml` | access reviews with entries, linked to Art. 32(1)(b) and Art. 32(4) |
| `tasks.yaml` | compliance tasks, linked to Art. 5(2) and Art. 24(1) |
| git history | `records-change-history.json`: who changed which record and when, linked to Art. 5(2) and Art. 24(1) |
| `system.yaml` | a draft `context.yaml` for the organization to complete: `services` from the product and customers sections, `boundaries` from architecture, `people` from team, `processes` from processes; `scope_statement`, `role`, `sites`, `outsourced` and `changes` are left empty |

Measures whose title or description mentions termination, offboarding or deprovisioning get the `terminations` population; onboarding, new hire, background check or screening get `hires`; nonconformity or corrective action get `nonconformities`. Confirm each in `testplan.csv`.

## Rules that matter here

- **Which framework file.** Without `framework`, the connector picks the file whose name matches the GDPR (`gdpr`, `dsgvo`, `general data protection`, `2016/679`). It prefers the separate "GDPR Criteria, AI Audited" copy that compliance-prep sets up for an AI Audit.
- **Provenance.** Everything is `obtained: client`. The organization keeps these files, so they are not pulled from a system of record. Prefer machine-generated exports inside `evidence/` (a consent platform export, a deletion-job log) over notes, and say in the workpaper what you relied on.
- **Dates.** Evidence and exports carry their git commit dates. A file committed after the period ended does not show the control operated in the period.
- **Change record.** The git log is the records' change record. Use it to test changes to the record of processing, policies and measures, approvals made in reviewed commits, and records edited after the fact.
- **No request or breach populations.** The records folder has no log of data subject requests, breaches or new processing that the connector turns into a population. If the organization keeps them, ask for them; to sample them in an audit of records over a period, ingest them as populations with the [folder](folder.md) connector.
- **Warnings to act on.**
  - Framework controls whose `ref` and `name` contain no recognizable provision.
  - Measures not linked to any provision.
  - A `people.yaml` without `contract_start`, which leaves the hires population empty.
  - A records folder that is not in git.
- **Description.** The draft `context.yaml` is evidence, not the report text, even when `system.yaml` is marked approved. Write `context.yaml` at the engagement root, with the processing in scope and the roles, as for any connector.
