# Folder

For teams without a compliance platform: the records are YAML files in a git repo, and
the evidence is files in `evidence/<measure id>/`. Every check runs, except the register
checks: here the files are the registers, and git history dates them.

## Setup

```bash
cp -R assets/folder-template <repo>/records
```

`prep.yaml`:

```yaml
platform: folder
options:
  path: records        # relative to prep.yaml
frameworks: [SOC 2]
ai_audit:
  framework: SOC 2
```

The layout is in the docstring of `scripts/connectors/folder.py`. Replace every example in
the template, and delete the example evidence files.

## Rules that matter here

- An AI Audit reads this folder directly with the audit skills' `records` connector
  (`init --connector records --option path=<folder>`). It audits the framework file named
  "<Framework> Criteria, AI Audited" when there is one. Give people a `contract_start`
  and `contract_end`, vendors an `added_at` and findings an `identified_on`: the audit
  samples from those dates. Put document text in `documents/<id>.md` so the audit can
  read the policy, not only its approval record.

- Set `updated_at` on a measure or risk whenever you change it. `RISK_OLDER_THAN_MEASURE`
  compares those dates.
- Approval and signature are the `approved_by`, `approved_at` and `signed_by` fields. Fill
  them only from a real approval, recorded in a reviewed commit by the approver.
- Change records through pull requests. The review and the merge are the change record.
- `tasks.yaml` is the only to-do list.
