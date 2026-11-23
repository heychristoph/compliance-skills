# Planning and sampling

`nis2.py plan` creates `testplan.csv` with one row per unit: each control in the entity's matrix, plus a `REQ-` unit for each in-scope requirement no control maps to. Complete every row, then run `nis2.py sample`, which draws the samples and writes workpaper skeletons. Sampling is seeded from `engagement.yaml`, so the same plan always gives the same sample, and anyone can reproduce it.

## Columns

| Column | Values | How to decide |
|---|---|---|
| `include` | `yes` | Always `yes`. An assessment and an audit both cover every requirement in scope; `sample` refuses `no`. |
| `frequency` | `annual`, `semiannual`, `quarterly`, `monthly`, `weekly`, `daily`, `multiple-daily`, `event`, `continuous` | How often the activity happens, from its description and the policy. "For each significant incident", "on onboarding a supplier", "when a patch is released" are `event`. A configuration that is always on, or a requirement met by a standing document, is `continuous`. |
| `nature` | `manual`, `automated`, `itdm` | `automated`: a system does it with no human step (MFA enforcement, log collection, backups). `itdm`: a person acts on system output (triaging a scan report, approving a patch from a feed). Otherwise `manual`. |
| `population` | `PO-...` artifact ID or empty | Required for `event` rows: the list of occurrences (e.g. `PO-significant-incidents` for reporting, `PO-vendors` for supplier onboarding, `PO-patches` for patching). Look at the population files in `bundle/manifest.json`. |
| `sample_size` | number or empty | Leave empty to use the table in `scripts/engine/sampling.yaml`. Override only with a reason in `notes`. |
| `notes` | text | Why you chose an unusual frequency, population or sample size. |

When the connector already filled a value, check it against the control description instead of trusting it. `REQ-` rows are prefilled from the catalog defaults in `assets/frameworks/nis2.yaml` and say so in `notes`; confirm them.

**Event-driven requirements without a population.** The catalog gives event-driven requirements (breach notification, data subject requests, incident reporting, joiners and leavers) the frequency `event`. An `event` row needs a population, and `plan` lists every `REQ-` row that has none. For each: name the population that lists the occurrences (`PO-...`), or, when there is none, set `continuous` and say in `notes` that the requirement is audited against its documented procedure and its latest record. Better still, ask whether a control covers it and was not mapped.

## Populations that matter for NIS2

| Population | Units it feeds | Completeness test against |
|---|---|---|
| Significant incidents (date: when the entity became aware) | Art. 23(1), 23(4)(a) to (d) | The full incident register with its significance classification |
| All incidents | Art. 21(2)(b), 23(3), IR.3.4 to IR.3.6 | Ticketing or SIEM case export |
| Changes | Art. 21(2)(e), IR.6.4 | Deployment or merge log |
| Security patches or advisories | IR.6.6 | Vendor advisory feed, patch management tool |
| Vulnerabilities | IR.6.10 | Scanner export |
| Supplier onboardings | Art. 21(2)(d), 21(3), IR.5.1 | Procurement or accounts payable ledger |
| Hires, terminations | Art. 21(2)(g), (i), IR.8.1, IR.10.2, IR.11.5, IR.12.5 | HR roster |
| Nonconformities | Art. 21(4) | Findings register, internal audit report |

## Audits (records over a period)

- Periodic activities: `sample` generates the occurrences in the records period (months, quarters, ISO weeks, days) and samples from them. Items look like `2026-Q2`, `2026-03`, `2026-W14`, `2026-05-12`, or `2026` for annual activities.
- Event activities: items are rows of the population file whose date falls in the period.
- Automated and continuous controls: one item, `instance-1`. Testing one instance is enough only if change management (IR.6.4) and access control (IR.11.2) are effective; note that dependency in the workpaper.
- An activity with no occurrences in the period gets an empty sample. Its workpaper concludes `not-audited`, with a scope limitation explaining that the circumstances requiring it did not occur. A period without any significant incident still needs the reporting procedure audited for design.

An audit needs records of the measures operating: at least one management body approval, the quarterly or periodic reporting to it, a risk assessment and an effectiveness review in or near the period. If the records period is too short for that, say so to the user before sampling.

## Assessments (documentation and readiness as of a date)

Every unit gets one item. Periodic activities get the item `latest`: find the most recent performance on or before the as-of date and cite it. Event activities get one random item from their population. Automated controls get `instance-1`. An assessment confirms that the measures are documented and in place, that the management body has approved them, and that the entity can report within the Art. 23 deadlines (procedure, authority channel, a reporting exercise). There is no population completeness test.

## Changing the plan

If you change a row after sampling, run `sample` again. It refuses to overwrite or remove a workpaper that already has results unless you pass `--force`, which discards those results. Never edit a workpaper's `plan` block directly; `validate` recomputes it and will reject the workpaper.
