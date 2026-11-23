# Folder connector

Builds the bundle from files on disk. Use it for platform exports, files the organization uploads, or any source without a dedicated connector.

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
├── context.yaml          processing scope and context (see ../engagement-folder.md)
├── populations/<name>.csv   first columns id,date; becomes PO-<name>
├── policies/<file>       policies, procedures, notices, DPA templates and other documents (kind: policy)
├── evidence/<id>/<file>  evidence, grouped by the control ID or provision ID it supports
└── evidence.csv          optional: path,controls,requirements,title,date,obtained,kind
```

- In `controls.csv`, `criteria` lists GDPR provision IDs, space- or comma-separated, as the catalog writes them (`Art.30(1) Art.32(1)(b) Art.12(3)`). Other spellings are recognized too: `Art. 30(1)`, `Article 33 (2)`, `Artikel 33 Abs. 1`. A whole article expands to every catalog entry under it (`Art. 32` becomes `Art.32(1)`, `Art.32(1)(a)` ... `Art.32(4)`), and a reference more specific than the catalog falls back to its parent (`Art. 30(1)(g)` becomes `Art.30(1)`). Control IDs must not look like provision IDs and must not start with `REQ-`.
- `population` names a file in `populations/` (`dsr` or `dsr.csv`). Typical populations: `dsr` (data subject requests), `incidents` (security incidents and breaches), `vendors` (new processors), `subprocessor-changes`, `projects` (new processing), `customer-offboardings`, `hires`, `terminations`. Each row needs `id` and `date`. The names in `populations/vendors.csv` may appear in the report.
- There is no Statement of Applicability for the GDPR. A `soa.csv` in the export is ignored; applicability follows from `roles` in `engagement.yaml`.
- Without `context.yaml`, ingest warns and `check` asks the organization for it.
- Files under `evidence/<control-id>/` are linked to that control. Files under `evidence/<provision-id>/` (e.g. `evidence/Art.30(1)/`, `evidence/Art.26(1)/`) are linked to that provision, for provisions no control covers; the folder name must be the catalog ID exactly. Name item evidence with the item ID first (`DSR-009_request-record.json`, `V-02_processor-onboarding.json`) so the auditor can find it.
- `evidence.csv` adds metadata for any file, keyed by its path relative to the export root: more controls, provisions, a title, the artifact's own date, and whether it was obtained directly.

## Converting a platform export

Most platforms can export an audit package (a zip of evidence plus a control list). Unzip it, write `controls.csv` from its control list with each control's GDPR mapping, add the records of processing, privacy notices, DPA templates and the breach procedure under `policies/`, the request log, breach register and vendor register as populations, and move files into `evidence/<control-id>/`. Keep original file names after the item ID. Record `obtained: direct` in `evidence.csv` for files the auditor downloaded itself.
