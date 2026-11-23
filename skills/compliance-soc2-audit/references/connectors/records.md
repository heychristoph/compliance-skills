# Records connector

Builds the bundle from a **compliance-prep records folder**: the YAML records and evidence files a company keeps in git when it has no compliance platform. Use it when the compliance-prep skill runs with `platform: folder`.

## Configure

```yaml
source:
  connector: records
  options:
    path: ../records      # the records folder, relative to the engagement folder or absolute
    framework: soc-2   # optional: framework id or file stem in frameworks/
```

`soc2.py init <dir> ... --connector records --option path=<records folder>`

## What it reads

| Records file | Bundle |
|---|---|
| `frameworks/<name>.yaml` | the audited framework. Each control's `ref` (`CC6.1`) becomes requirement IDs |
| `measures.yaml` | `controls.csv`: one control per measure, mapped to the requirements of the framework controls that list it |
| `evidence/<measure id>/<file>` | evidence linked to that control, dated by the git commit that added the file |
| `documents.yaml`, `documents/<id>.md` | policies: version, publication, approval and signatures, plus the text when the file exists |
| `people.yaml` (`contract_start`, `contract_end`) | `hires` and `terminations` populations for the period |
| `vendors.yaml` (`added_at`) | `vendors` population and the vendor register with DPA status |
| `findings.yaml` (`identified_on`) | `nonconformities` population and the findings register |
| `risks.yaml`, `assets.yaml`, `data.yaml`, `audits.yaml`, `access-reviews.yaml`, `tasks.yaml` | register exports, linked to the requirements they support |
| git history | `records-change-history.json`: who changed which record and when |
| `system.yaml` | a draft `system.yaml` for the organization to complete |

## Rules that matter here

- **Which framework file.** Without `framework`, the connector picks the file whose name matches the audited framework. It prefers the separate "<Framework> Criteria, AI Audited" copy that compliance-prep sets up for an AI Audit.
- **Provenance.** Everything is `obtained: client`. The organization keeps these files, so they are not pulled from a system of record. Prefer machine-generated exports inside `evidence/` (an identity provider's MFA export, a CI log) over notes, and say in the workpaper what you relied on.
- **Dates.** Evidence and exports carry their git commit dates. A file committed after the period ended does not show the control operated in the period.
- **Change record.** The git log is the records' change record. Use it to test changes to policies and measures, approvals made in reviewed commits, and records edited after the fact.
- **Warnings to act on.**
  - Measures not linked to any requirement.
  - A `people.yaml` without `contract_start`, which leaves the hires population empty.
  - A records folder that is not in git.
- **Description.** The draft `system.yaml` is evidence, not the report text. Write `system.yaml` at the engagement root, as for any connector.
