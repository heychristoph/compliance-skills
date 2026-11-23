# Planning and sampling

`app.py plan` creates `testplan.csv` with one row per unit: each control in the organization's matrix (when a records folder provides one), plus a `REQ-` unit for each requirement in scope that no control maps to. With `intake` alone every unit is a `REQ-` unit, one per requirement. Complete every row, then run `app.py sample`, which writes the workpaper skeletons. Sampling is seeded from `engagement.yaml`, so the same plan always gives the same result.

Run `plan` only after `detect` and the first `ingest`: `detect` decides which optional requirements apply, and `plan` creates units for exactly the requirements in scope at that moment. If you change `roles` or `include_optional` later, run `plan` and `sample` again.

## Columns

| Column | Values | How to decide |
|---|---|---|
| `include` | `yes` | Every unit, always. An app assessment covers every requirement in scope; `sample` refuses `no`. |
| `frequency` | `continuous`, `annual`, `event`, ... | `REQ-` rows are prefilled from the catalog (`plan` in `assets/frameworks/app.yaml`) and say so in `notes`. Configuration that is always on (RLS, auth settings, bucket flags, keys in code) is `continuous`. A document or procedure (TOMs, DPA, retention schedule, restore test, security test) is `annual`. |
| `nature` | `automated`, `manual`, `itdm` | `automated`: the platform or code enforces it (RLS, MFA enforcement, retention jobs). `manual`: a person does it (access reviews, restore tests, breach notice). `itdm`: a person acts on system output (triaging Dependabot alerts). |
| `population` | empty | An assessment as of a date has no populations to sample. Leave it empty. |
| `sample_size` | empty | Leave it empty. |
| `notes` | text | Why you changed a catalog default. |

Confirm each prefilled row against the requirement; do not just accept it.

**Event-driven requirements.** The catalog gives DP-INC-02 (breach notice to the controller) the frequency `event`, and `plan` lists it because it has no population. At a point in time there is nothing to sample: set `continuous` and write in `notes` "no population at a point in time; the notice procedure, the contractual deadline and the latest record, if any, are assessed". Do the same for any other `event` row.

## What the sample is

The only audit type is `assessment`, as of `as_of`. Every unit gets one item:

- `continuous` or `automated` units get `instance-1`: the configuration or code as it stands on the date. One instance is enough for a configuration read on that date; note in the workpaper that it says nothing about the configuration before or after.
- Other units (`annual`, `manual`) get `latest`: the most recent version of the document or the most recent performance (the last restore test, the current DPA) on or before the date.

There is no population completeness test.

## Changing the plan

If you change a row after sampling, run `sample` again. It refuses to overwrite or remove a workpaper that already has results unless you pass `--force`, which discards those results. Never edit a workpaper's `plan` block; `validate` recomputes it and rejects the workpaper.
