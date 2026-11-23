# Grading findings and concluding

Run `python scripts/nis2.py rollup <engagement>` to see each requirement with its units and their conclusions, every deviation still to grade, and the requirements out of scope for the engagement's entity types (`review/rollup.md`). Check that list against the classification evidence: a requirement left out because the entity was classified wrongly is a scope problem. Then group the deviations into findings, grade each one, and write `findings.json`.

## From deviations to findings

A deviation is a fact in one workpaper. A finding is your judgment about a requirement. One finding can grade several deviations (two late early warnings are one nonconformity against Art. 23(4)(a)), and one deviation can belong to only the finding that best describes it.

Each finding is recorded against **one** requirement, the one that was not fulfilled, with:
- a **statement** of the nonconformity: the requirement and what was not fulfilled;
- the **objective evidence**: counts, item IDs, dates, times and documents, specific enough that the entity can check it;
- links to the workpaper **deviations** it grades, and the **evidence** artifact IDs.

For a digital provider, record a finding against the most specific requirement: the Annex section (`IR.6.6` for a late patch) rather than the Art. 21(2) point it details, unless the Article itself is what was not met (no management body approval is `Art.20(1)`, a missed deadline is `Art.23(4)(a)`).

Do not suggest the cause of a nonconformity or its solution. Art. 21(4) requires the entity to take corrective measures; it analyses the cause.

Every deviation must be graded, and every `design-gap` must be a major or minor nonconformity. `validate --final` checks both.

## Grades

| Grade | ID | When |
|---|---|---|
| `major` | `NC-01` | An obligation is not met in a way that prevents the entity from demonstrating that its measures, governance or reporting achieve their purpose. Typical: a required measure is absent or has broken down (no risk assessment, no incident handling or reporting procedure, no supplier security at all); the management body has not approved the measures or receives no reporting; a significant incident was not reported, or was not recognized as significant; several minor nonconformities against the same requirement that together show a systemic failure; a failure that left a serious risk untreated (critical vulnerabilities on internet-facing systems unpatched for months). |
| `minor` | `NC-02` | An obligation was not fulfilled, but the measure otherwise works: an isolated missed deadline (one early warning sent after 31 hours while the others were on time), a missing or incomplete record, one supplier onboarded without an assessment, one member of the management body without training. |
| `ofi` | `OFI-01` | The obligation is met, but something could be better. Use it for a deviation only when the obligation is still met, for example when the entity's own monitoring already found the lapse and corrective measures under Art. 21(4) are in progress; say so in the statement. An OFI may also point to a stricter national rule the entity does not yet meet. |

When unsure between two grades, choose the more serious one and explain the judgment in the statement. In an assessment, findings are gaps as of the date; grade them as they would be graded if still present in an audit.

For each requirement with deviations, weigh:
- **Rate and pattern.** One late item in a large sample may be isolated; repeated failures, or failures in a small population (there are rarely more than a handful of significant incidents), point to a process that did not operate.
- **Cause.** A one-off human error is different from a missing process (a quarterly report to the management body that never happened).
- **Detection.** Did the entity's own effectiveness assessment (Art. 21(2)(f)) or corrective measures (Art. 21(4)) find and handle it? That is evidence the measures work.
- **Impact.** Could the failure have allowed the risk the requirement addresses, or delayed the authority's response to a significant incident?

National law is not graded. A national rule stricter than the Directive can be an OFI, never a nonconformity.

## The conclusion

| `recommendation` | When | Printed (audit) | Printed (assessment) |
|---|---|---|---|
| `recommended` | No nonconformities and no scope limitations. OFIs are allowed. | The required measures, governance and reporting were implemented and operated effectively over the period. | Documented and in place as of the date; operation not yet shown. |
| `recommended-with-actions` | Minor nonconformities only (or a limited scope), no major. | As above, except for the minor nonconformities; Art. 21(4) corrective measures are due and not verified. | In place except for the gaps in Section III. |
| `not-recommended` | At least one major nonconformity. | Compliance with the audited obligations was not demonstrated; corrective measures must be implemented and verified. | Not demonstrably in place; resolve before an audit of the measures in operation. |
| `no-conclusion` | Scope limitations so significant that no conclusion can be formed. | No conclusion. | No conclusion. |

`validate --final` checks that the recommendation follows from the grades. None of the printed conclusions says the entity complies with national law or is a decision of a competent authority.

## findings.json

```json
{
  "schema_version": 1,
  "findings": [
    {
      "id": "NC-01",
      "grade": "minor",
      "requirement": "Art.23(4)(a)",
      "statement": "An early warning was not submitted within 24 hours of the entity becoming aware of a significant incident.",
      "objective_evidence": "For 1 of 3 significant incidents in the period (INC-2026-004), the entity became aware on 3 March 2026 at 08:10 and submitted the early warning through the BSI-Portal on 4 March 2026 at 15:30, 31 hours 20 minutes later. The incident notification and the final report were on time.",
      "deviations": [{"control": "C-10", "item": "INC-2026-004"}],
      "evidence": ["EV-0102", "EV-0098"],
      "management_response": null
    }
  ],
  "scope_limitations": [],
  "recommendation": "recommended-with-actions",
  "summary": "The entity has established cybersecurity risk-management measures approved and overseen by the management body, assesses their effectiveness, and reports significant incidents to the competent authority, except as described in the minor nonconformities in Section III.",
  "scope_appropriate": true,
  "scope_note": "",
  "prepared_by": "<agent / model>"
}
```

- `summary` is printed as the statement on the implementation and effectiveness of the measures. Write it in the auditor's voice: what is in place, how effective it is, and where it falls short.
- `scope_appropriate` and `scope_note` are the conclusion on the audit scope and the entity's classification. A classification the evidence does not support (an essential entity that classified itself as important, a cloud provider that did not recognize itself as a digital provider), or a scope that leaves out services or establishments the classification covers, is not appropriate. Use `scope_note` also to name member states with jurisdiction whose national law the catalog does not cover.
- `management_response` stays `null` unless the entity provided its corrective measures; it prints in Section VI.
- Every string here is printed. It names no one but `management.name`, and contains no email address or phone number.
