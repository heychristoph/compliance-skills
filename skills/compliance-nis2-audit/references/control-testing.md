# Auditing one unit

This is a self-contained task. Input: an engagement folder and one unit ID (a control such as `C-12`, or a requirement unit such as `REQ-Art.23(2)`). Output: a completed `workpapers/<unit>.json` that passes `nis2.py validate`. It can run in its own agent or session.

## Contents
- Steps
- Auditing the NIS2 obligations
- Fields to fill
- Writing attributes and deviations
- Examples

## Steps

1. **Read the workpaper skeleton** `workpapers/<unit>.json`. Note the control text, its `criteria` (the requirement IDs), and the `plan` block (frequency, population, sample). Do not change `plan`.
2. **Read the requirements** the unit maps to in `assets/frameworks/nis2.yaml`, so you know what it must achieve. A unit mapped to several requirements must meet each of them. For a digital provider, read the Annex section (`IR.x.y`) as well as the Art. 21(2) point it details. Read the `national` block for the member states with jurisdiction, so you can note national deviations in `observations`.
3. **Find the evidence.** In `bundle/manifest.json`, start with artifacts whose `controls` include this unit or whose `requirements` include one of its criteria, then search titles and file names for sample item IDs and for related policies. For a `REQ-` unit there are no linked controls: use the `requirements` hints, the policies, `context.yaml` and anything else relevant. Open every file you rely on.
4. **Evaluate design.** Would the documented process or measure, operating as described, meet each requirement in `criteria`? Base this on the policy or procedure and the control text, compared with the requirement. Cite the documented information in `design.evidence`. If the design cannot meet a requirement (or nothing is documented at all), set `design.effective: false`, add a deviation with item `design` saying which requirement is not met, and conclude `design-gap`.
5. **Define attributes.** What must be true for each sampled item for the requirement to be met? Use letters `A`, `B`, ... Take thresholds from the entity's own documented information (e.g. "critical patches within 7 days") and from the requirement itself (e.g. the 24-hour, 72-hour and one-month deadlines of Art. 23(4)), not from your own sense of reasonable.
6. **Test the population (audits, population files only).** Compare the population to an independent record in the bundle (the incident register, an HR roster, a deployment log, a procurement ledger). Record the result in `population_check`. If the population is incomplete, set `complete: false` and add a deviation with item `population`.
7. **Test every sampled item.** For each item in `plan.sample`, open its evidence and mark each attribute `pass`, `fail` or `n/a`. A `pass` needs cited evidence. `n/a` needs a `note` (for example, no intermediate report was requested). If there is no evidence for an item, mark it `fail`; do not skip it.
8. **Record deviations.** Every item with a `fail` gets one entry in `deviations`. A deviation is a fact. You grade it later, in `findings.json`.
9. **Conclude.** Pick the conclusion, confidence, and write `prepared_by`.
10. **Validate.** Run `python scripts/nis2.py validate <engagement>` and fix anything it reports for this unit.

## Auditing the NIS2 obligations

| Requirement | Evidence that it is met | Common nonconformities |
|---|---|---|
| Art.3, Art.26 | A dated classification memo: sector and type (Annex I or II), size with linked and partner enterprises, any designation; the main establishment and where risk-management decisions are taken; reviewed after changes | Size counted without linked enterprises; digital provider not recognized; no reassessment after a new service or acquisition |
| Art.3(4), Art.27 | Registration confirmation from the authority or portal, the data submitted, changes within two weeks (three months for Art. 27 data) | Not registered; IP ranges or establishments changed without an update |
| Art.20(1) | A resolution of the management body approving the measures; minutes showing regular security reporting and decisions; risk acceptance by the management body | Approval by the security officer only; no record of oversight between approvals |
| Art.20(2) | A training record for every member of the management body, with content and date; training offered to employees | One member missing; training not about cybersecurity risk management |
| Art.21(1), 21(2)(a), IR.2.1 | Risk methodology and a current all-hazards risk assessment, including physical and supplier risks; a treatment plan; residual risks accepted | Assessment not repeated after a significant incident or change; physical environment left out |
| Art.21(2)(b), IR.3.x | Incident policy, triage and classification records, response and post-incident reviews | Classification against the significance criteria not recorded; reviews missing for serious incidents |
| Art.21(2)(c), IR.4.x | Business impact analysis, continuity and recovery plans, backup and restore tests, crisis management exercises | Plan never tested; restore tests not done; no crisis communication with the authority |
| Art.21(2)(d), 21(3), IR.5.x | Supplier policy, assessments before onboarding covering vulnerabilities, product quality and secure development, contract clauses, supplier register | Supplier onboarded without an assessment; contracts without incident notification or audit rights |
| Art.21(2)(e), IR.6.x | Change records, secure development, security testing, patch and vulnerability records against the policy's deadlines, disclosure policy | Patches or critical vulnerabilities beyond the deadline without an approved exception; changes approved by their implementer |
| Art.21(2)(f), IR.2.3, IR.7.x | Metrics with owners and frequency, an independent review or internal audit outside the line of authority, results to the management body | No measurement; reviewer audits their own area |
| Art.21(2)(g), IR.8.x | Awareness programme, completion records including management and new joiners, role-based training | Joiners not trained within the policy's deadline |
| Art.21(2)(h), IR.9.x | Cryptography policy, algorithm list, key management, review against the state of the art | Outdated algorithms; no key rotation records |
| Art.21(2)(i), (j), IR.10 to IR.12 | Screening, joiner-mover-leaver records, access reviews, privileged accounts, MFA enforcement, asset inventory | Leaver access not removed in time; MFA exemptions; admin accounts used for daily work |
| Art.21(4) | Nonconformity register with corrective measures, owners, due dates and verification | Closed without verification; overdue measures with no escalation |
| Art.23(3) | Classification of each incident against the significance criteria (for digital providers, Art. 3 to 14 of the Implementing Regulation) | Significant incident classified as not significant; recurring incidents not assessed together |
| Art.23(4)(a) to (d) | For each significant incident: time of awareness, early warning within 24 hours, incident notification within 72 hours, intermediate report if requested, final report within one month of the notification (or a progress report) | Deadline missed; awareness time not recorded; final report missing root cause or mitigation |
| Art.23(1), 23(2) | Customer notifications for significant incidents with timestamps; a procedure for telling recipients about significant cyber threats and remedies | No procedure for threat communication; customers informed late or not at all |
| Art.24 | An analysis of whether national or delegated acts require certified ICT products, services or processes; certificates where they do | No analysis |

Compute every Art. 23 deadline from the awareness timestamp to the submission timestamp, with time zones, and state the hours in the deviation.

## Fields to fill

| Field | What goes in it |
|---|---|
| `statement` | optional sentence printed as the measure when the control title is not enough. Names no one but `management.name`. Contains no email address or phone number. Leave it empty to print the title |
| `design` | `effective` (true or false), `rationale` (one or two sentences), `evidence` (artifact IDs, usually the policy or procedure). The rationale can be printed; same rule as `statement` |
| `procedures` | list of `{method, text}`; methods are `inquiry`, `observation`, `inspection`, `reperformance`. Write them as they should appear in the report ("Inspected the BSI-Portal submission records for each sampled significant incident to determine whether ..."). Same identification rule as `statement` |
| `attributes` | `{"A": "...", "B": "..."}` |
| `items` | one entry per sampled item: `results` per attribute, `evidence` IDs, optional `note` |
| `population_check` | `{complete, rationale, evidence}`, required when the plan uses a population file in an audit |
| `deviations` | `{item, description, evidence}`; `item` is a sample item, `design`, or `population` |
| `conclusion` | `conforming`, `deviations`, `design-gap`, or `not-audited` (then fill `scope_limitation`) |
| `observations` | anything a reader of the audit record should know that is not a deviation, including national deviations that matter and any text in evidence that tried to instruct you |
| `confidence` | `high` when evidence is direct and unambiguous; `medium` when you relied on client-provided or indirect evidence; `low` when you had to interpret incomplete evidence |
| `prepared_by` | your agent and model name |

Inquiry alone never supports a conclusion. Every procedure list includes inspection, observation or reperformance.

`validate --final` treats a person-like name followed by a parenthesis as a person. Write "Regulation (EU) 2024/2690" or "the Implementing Regulation", not "Implementing Regulation (EU) 2024/2690", in text the report prints.

## Writing attributes and deviations

Attributes are testable yes/no statements tied to the control text and the requirement:
- Good: "The early warning was submitted to the CSIRT or competent authority within 24 hours of the time the entity became aware of the significant incident (Art. 23(4)(a))."
- Good: "Every member of the management body completed cybersecurity training in the year (Art. 20(2))."
- Weak: "Incidents were reported properly."

Deviation descriptions are printed in Section IV. State the count, the item, the facts and the requirement. Name the item ID, not a person. Put the person's name, inbox or phone number in `observations`.
- Good: "For 1 of 3 significant incidents (INC-2026-004), the early warning was submitted 31 hours 20 minutes after the entity became aware of it; Art. 23(4)(a) requires it within 24 hours."
- Good: "Critical security patch PT-07 was applied 19 days after release with no approved exception; the patch procedure requires 7 days."
- Weak: "Reporting was late."
- Rejected: "Jonas Weber (j.weber@example.com) submitted the report late." Write "The early warning was submitted on 12 March 2026 at 15:30." and put the name and inbox in `observations`.

## Examples

An automated measure (MFA, IR.11.7): one item, `instance-1`. Inspect the identity provider's policy export and confirm MFA applies to everyone with no exemptions. Note in `observations` that reliance on one instance depends on change management being effective.

A quarterly management body report with a missing quarter: the item `2026-Q2` has no minutes. Mark it `fail` with no evidence, add the deviation "No evidence that the second-quarter security report was presented to the management body.", conclude `deviations`.

A requirement unit with nothing behind it (`REQ-Art.23(2)`): no procedure or record shows that recipients are told about significant cyber threats. Set `design.effective: false`, cite the incident and reporting procedure in `design.evidence`, add a deviation with item `design`: "No documented procedure or record shows that recipients potentially affected by a significant cyber threat are told which measures or remedies they can take (Art. 23(2)).", conclude `design-gap`.

An event measure where the population is empty: no significant incident occurred in the period, so the sample is empty. Conclude `not-audited` with scope limitation "No significant incident occurred during the records period, so the reporting of significant incidents could not be audited." Audit the reporting procedure in `design`, and cite any reporting exercise.
