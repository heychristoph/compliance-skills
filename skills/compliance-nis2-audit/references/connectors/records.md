# Records connector

Builds the bundle from a **compliance-prep records folder**: the YAML records and evidence files a company keeps in git when it has no compliance platform. Use it when the compliance-prep skill runs with `platform: folder`.

## Configure

```yaml
source:
  connector: records
  options:
    path: ../records      # the records folder, relative to the engagement folder or absolute
    framework: nis2       # optional: framework id or file stem in frameworks/
```

`nis2.py init <dir> ... --entity-types important,digital-providers --connector records --option path=<records folder>`

## What it reads

| Records file | Bundle |
|---|---|
| `frameworks/<name>.yaml` | the audited framework. Each control's `ref` (`Art.21(2)(d)`, `Art. 23(4)`, `IR.6.6`) or, failing that, its name becomes requirement IDs. `applicable` and `justification` are not used: applicability comes from `entity_types` |
| `measures.yaml` | `controls.csv`: one control per measure, mapped to the requirements of the framework controls that list it |
| `evidence/<measure id>/<file>` | evidence linked to that control, dated by the git commit that added the file |
| `documents.yaml`, `documents/<id>.md` | policies: version, publication, approval and signatures, plus the text when the file exists |
| `people.yaml` (`contract_start`, `contract_end`) | `hires` and `terminations` populations for the period |
| `vendors.yaml` (`added_at`) | `vendors` population and the supplier register, linked to Art. 21(2)(d), 21(3) and IR.5.2 |
| `findings.yaml` (`identified_on`) | `nonconformities` population and the findings register, linked to Art. 21(4) and IR.3.6 |
| `risks.yaml`, `assets.yaml`, `data.yaml`, `audits.yaml`, `access-reviews.yaml`, `tasks.yaml` | register exports, linked to the requirements they support (risks to Art. 21(1), 21(2)(a), IR.2.1; audits to Art. 21(2)(f), IR.2.3, IR.7.1; access reviews to Art. 21(2)(i), IR.11.2; tasks to Art. 20(1), IR.2.2) |
| git history | `records-change-history.json`: who changed which record and when |
| `system.yaml` | a draft `context.yaml` (`services` from product and customers, `boundaries` from architecture, `people`, `processes`) for the entity to complete |

## Rules that matter here

- **Which framework file.** Without `framework`, the connector picks the file whose name matches NIS2 ("NIS2", "NIS 2", "NIS-2" or "2022/2555"). It prefers the separate "<Framework> Criteria, AI Audited" copy that compliance-prep sets up for an AI Audit.
- **Provenance.** Everything is `obtained: client`. The entity keeps these files, so they are not pulled from a system of record. Prefer machine-generated exports inside `evidence/` (an identity provider's MFA export, the authority portal's submission receipt, a CI log) over notes, and say in the workpaper what you relied on.
- **Dates.** Evidence and exports carry their git commit dates. A file committed after the period ended does not show the measure operated in the period, and a reporting record committed days after the incident is not evidence of when the report was submitted: look for the submission timestamp in the record itself.
- **Incidents.** The records folder has no incident register or significant incident population. Ask for them (as files under the reporting measure's evidence folder, or through the folder connector) before planning the Art. 23 units.
- **Change record.** The git log is the records' change record. Use it to test changes to policies and measures, approvals made in reviewed commits, and records edited after the fact.
- **Warnings to act on.**
  - Measures not linked to any requirement.
  - Framework controls with no recognizable NIS2 requirement ID.
  - A `people.yaml` without `contract_start`, which leaves the hires population empty.
  - A records folder that is not in git.
- **Description.** The draft `context.yaml` is evidence, not the report text. It has no `scope_statement` or `role`. Write `context.yaml` at the engagement root, with the classification and its reason, as for any connector.
