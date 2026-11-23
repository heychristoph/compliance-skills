# Folder connector

Builds the bundle from files on disk. Use it for platform exports, files the entity uploads, or any source without a dedicated connector.

## Configure

```yaml
source:
  connector: folder
  options:
    path: export          # relative to the engagement folder, or absolute
    obtained: client      # default provenance: client (provided) or direct (auditor pulled it)
```

## Expected layout

```
export/
├── controls.csv          required: id,title,description,criteria[,owner,frequency,nature,population]
├── context.yaml          entity scope and context (see ../engagement-folder.md)
├── populations/<name>.csv   first columns id,date; becomes PO-<name>
├── policies/<file>       policies, procedures and other documents (kind: policy)
├── evidence/<id>/<file>  evidence, grouped by the control ID or requirement ID it supports
└── evidence.csv          optional: path,controls,requirements,title,date,obtained,kind
```

- In `controls.csv`, `criteria` lists NIS2 requirement IDs, space- or comma-separated: `Art.3`, `Art.20(1)`, `Art.21(2)(d)`, `Art.23(4)(a)`, Annex sections of Implementing Regulation (EU) 2024/2690 as `IR.6.6`. Free text such as "Art. 21(2)(d)", "Article 23 (4)", "Artikel 21 Abs. 2" or "IR 6.10" is recognized too; a whole article or paragraph expands to the catalog entries under it (`Art.23(4)` becomes the four reporting entries). Control IDs must not look like requirement IDs and must not start with `REQ-`.
- `population` names a file in `populations/` (`significant-incidents` or `significant-incidents.csv`).
- There is no Statement of Applicability; a `soa.csv` is ignored. Applicability comes from `entity_types` in `engagement.yaml`.
- Files under `evidence/<control-id>/` are linked to that control. Files under `evidence/<requirement-id>/` (e.g. `evidence/Art.24/`, `evidence/IR.9.3/`) are linked to that requirement, for requirements no control covers. Name item evidence with the item ID first (`INC-2026-004_reporting-record.json`) so the auditor can find it.
- `evidence.csv` adds metadata for any file, keyed by its path relative to the export root: more controls, requirements, a title, the artifact's own date, and whether it was obtained directly.

## Converting a platform export

Most platforms can export an audit package (a zip of evidence plus a control list). Unzip it, write `controls.csv` from its control list with each control's NIS2 mapping (Article point or Annex section), and move files into `evidence/<control-id>/`. Keep original file names after the item ID. Record `obtained: direct` in `evidence.csv` for files the auditor downloaded itself. Export reporting records (submissions to the CSIRT or authority portal) with their timestamps; a screenshot without the time of submission does not show the deadline was met.
