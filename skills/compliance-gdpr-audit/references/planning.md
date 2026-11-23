# Planning and sampling

`gdpr.py plan` creates `testplan.csv` with one row per unit: each control in the organization's matrix, plus a `REQ-` unit for each in-scope obligation no control maps to. Complete every row, then run `gdpr.py sample`, which draws the samples and writes workpaper skeletons. Sampling is seeded from `engagement.yaml`, so the same plan always gives the same sample, and anyone can reproduce it.

## Columns

| Column | Values | How to decide |
|---|---|---|
| `include` | `yes` | Every unit, always. A GDPR assessment or audit covers every obligation that applies to the roles; `sample` refuses `no`. |
| `frequency` | `annual`, `semiannual`, `quarterly`, `monthly`, `weekly`, `daily`, `multiple-daily`, `event`, `continuous` | How often the activity happens, from its description and the policy. "For each request", "for each new processor", "when a breach occurs", "before each new processing activity" are `event`. A configuration that is always on (encryption, MFA, a consent setting), or an obligation met by a standing document, is `continuous`. Reviews of the record of processing, notices and the DPA template are usually `annual`. |
| `nature` | `manual`, `automated`, `itdm` | `automated`: a system does it with no human step (deletion jobs, encryption, the unsubscribe link). `itdm`: a person acts on system output (reviewing a deletion-job report). Otherwise `manual`. |
| `population` | `PO-...` artifact ID or empty | Required for `event` rows: the list of occurrences. Look at the population files in `bundle/manifest.json`. |
| `sample_size` | number or empty | Leave empty to use the table in `scripts/engine/sampling.yaml`. Override only with a reason in `notes`. |
| `notes` | text | Why you chose an unusual frequency, population or sample size. |

When the connector already filled a value, check it against the control description instead of trusting it. `REQ-` rows are prefilled from the catalog defaults in `assets/frameworks/gdpr.yaml` and say so in `notes`; confirm them.

**Event-driven requirements without a population.** The catalog gives event-driven requirements (breach notification, data subject requests, incident reporting, joiners and leavers) the frequency `event`. An `event` row needs a population, and `plan` lists every `REQ-` row that has none. For each: name the population that lists the occurrences (`PO-...`), or, when there is none, set `continuous` and say in `notes` that the requirement is audited against its documented procedure and its latest record. Better still, ask whether a control covers it and was not mapped.

## Populations that matter for the GDPR

| Population | Typical source | Units that sample it |
|---|---|---|
| Data subject requests (`dsr`) | privacy request log, ticket queue | Art. 12(3) to 12(6), Art. 15 to 21 |
| Security incidents and breaches (`incidents`) | breach register, incident tool | Art. 33, Art. 34 |
| New processors (`vendors`) | vendor register, procurement | Art. 28(1), 28(3), Chapter V |
| Sub-processor changes | sub-processor list and customer notices | Art. 28(2), 28(4) |
| New processing, features or projects | privacy screenings, DPIA register | Art. 25, Art. 35 |
| Customer contract ends | customer offboardings | Art. 28(3)(g) |
| Hires and terminations | HR system | Art. 28(3)(b), Art. 32(4), Art. 32(1)(b) |

The test of a population's completeness (see [control-testing.md](control-testing.md)) needs an independent record: the privacy inbox for requests, the incident tool or support tickets for breaches, accounts payable or the SSO app list for processors, the HR roster for staff.

## Audits of records over a period (audit)

- Periodic activities: `sample` generates the occurrences in the records period (months, quarters, ISO weeks, days) and samples from them. Items look like `2026-Q2`, `2026-03`, `2026-W14`, `2026-05-12`, or `2026` for annual activities.
- Event activities: items are rows of the population file whose date falls in the period.
- Automated and continuous controls: one item, `instance-1`. Testing one instance is enough only if change management and access control over the system are effective; note that dependency in the workpaper.
- An activity with no occurrences in the period gets an empty sample. Its workpaper concludes `not-audited`, with a scope limitation explaining that the circumstances requiring it did not occur (for example, no personal data breach occurred in the period).

If the records period is too short for the processes to have operated (no request, no new processor, no review in the period), say so to the user before sampling; an assessment may be the better audit type.

## Assessments (documentation and readiness as of a date)

Every unit gets one item. Periodic activities get the item `latest`: find the most recent performance on or before the as-of date and cite it. Event activities get one random item from their population. Automated controls get `instance-1`. An assessment confirms that the records of processing, policies, notices, contracts and procedures exist and meet the Regulation, and that the processes have started. There is no population completeness test.

## Changing the plan

If you change a row after sampling, run `sample` again. It refuses to overwrite or remove a workpaper that already has results unless you pass `--force`, which discards those results. Never edit a workpaper's `plan` block directly; `validate` recomputes it and will reject the workpaper.
