# Grading findings and concluding

Run `python scripts/gdpr.py rollup <engagement>` to see each obligation with its units and their conclusions, every deviation still to grade, and the obligations out of scope for the engagement's roles (`review/rollup.md`). Check that list: an obligation excluded by role must really belong to another role. Then group the deviations into findings, grade each one, and write `findings.json`.

## From deviations to findings

A deviation is a fact in one workpaper. A finding is your judgment about a provision. One finding can grade several deviations (three requests answered late are one nonconformity against Art. 12(3)), and one deviation belongs to only the finding that best describes it.

Each finding is recorded against **one** provision, the one that was not fulfilled, with:
- a **statement** of the nonconformity: the provision and what was not fulfilled;
- the **objective evidence**: counts, item IDs, dates and documents, specific enough that the organization can check it;
- links to the workpaper **deviations** it grades, and the **evidence** artifact IDs.

Do not suggest the cause of a nonconformity or its solution. Do not assess fines, liability, or whether the organization must now notify a supervisory authority or data subjects; that is legal advice. The organization analyses the cause and decides what to do.

Every deviation must be graded, and every `design-gap` must be a major or minor nonconformity. `validate --final` checks both.

## Grades

| Grade | ID | When |
|---|---|---|
| `major` | `NC-01` | A required process or record is absent or has broken down, or the rights of data subjects are left unprotected. Typical: no record of processing activities (Art. 30); no breach procedure or breach register (Art. 33(5)); a notifiable breach never notified (Art. 33(1)); a processor processing personal data with no Art. 28(3) contract; high-risk processing started without a DPIA (Art. 35(1)); a regular third-country transfer with no Chapter V mechanism (Art. 44, 46); a processing activity with no lawful basis (Art. 6(1)); requests from data subjects routinely unanswered; a DPO required but not designated (Art. 37); several minor nonconformities against the same provision that together show a systemic failure. |
| `minor` | `NC-02` | An obligation was not met, but the process that meets it exists and otherwise works: an isolated late answer to a request, one breach notified after 72 hours with no reasons recorded, a field missing from some entries of the record of processing, an item missing from a notice, one late access removal. |
| `ofi` | `OFI-01` | The obligation is met, but something could be better. Use it for a deviation only when the obligation is still met, for example when the organization's own monitoring found the lapse and corrected it before it affected a data subject; say so in the statement. |

When unsure between two grades, choose the more serious one and explain the judgment in the statement. In an assessment, findings are gaps as of the review date; grade them as they would be graded in an audit of records over a period.

For each provision with deviations, weigh:
- **Rate and pattern.** One late item in a large sample may be isolated; repeated failures, or failures in a small population, point to a process that did not operate.
- **Cause.** A one-off error is different from a missing process (a record of processing that was never kept, a DPIA procedure nobody follows).
- **Detection.** Did the organization's own monitoring, the DPO or an internal review find and handle it? That is evidence that accountability works.
- **Impact on data subjects.** Could the failure affect the rights and freedoms of the people whose data it is: data exposed, a right denied, processing they were not told about?

## The conclusion

| `recommendation` | When | Printed |
|---|---|---|
| `recommended` | No nonconformities and no scope limitations. OFIs are allowed. | Compliant: the processing complied with the obligations that apply to the roles, as far as the evidence examined shows. |
| `recommended-with-actions` | Minor nonconformities only (or a limited scope), no major. | Compliant with corrective actions: each minor nonconformity requires correction and corrective action. |
| `not-recommended` | At least one major nonconformity. | Not compliant: compliance cannot be concluded until correction and corrective action for each major nonconformity are implemented and verified. |
| `no-conclusion` | Scope limitations so significant that no conclusion can be formed. | No conclusion. |

An assessment concludes as of the review date; an audit concludes on the records period. `validate --final` checks that the recommendation follows from the grades.

## findings.json

```json
{
  "schema_version": 1,
  "findings": [
    {
      "id": "NC-01",
      "grade": "major",
      "requirement": "Art.28(3)",
      "statement": "Processing by a processor was not governed by a contract setting out the terms Art. 28(3) requires.",
      "objective_evidence": "For 1 of 5 new processors sampled (V-02, text analytics), personal data has been processed since 9 February 2026; the onboarding record shows the data processing agreement was sent for signature and not returned.",
      "deviations": [{"control": "C-10", "item": "V-02"}],
      "evidence": ["EV-0061"],
      "management_response": null
    },
    {
      "id": "NC-02",
      "grade": "minor",
      "requirement": "Art.12(3)",
      "statement": "Requests from data subjects were not always answered within one month of receipt.",
      "objective_evidence": "For 1 of 5 requests sampled (DSR-009), the answer was sent 45 days after receipt with no extension notified. The request log also omits an erasure request the privacy inbox shows was received on 14 April 2026.",
      "deviations": [{"control": "C-06", "item": "DSR-009"}, {"control": "C-06", "item": "population"}],
      "evidence": ["EV-0035", "EV-0040"],
      "management_response": null
    }
  ],
  "scope_limitations": [],
  "recommendation": "not-recommended",
  "summary": "Data protection is organized and most processes operate as documented: the records of processing, notices, request handling and breach management are in place. The major nonconformity in Section III shows processing by a processor with no data processing agreement.",
  "scope_appropriate": true,
  "scope_note": "",
  "prepared_by": "<agent / model>"
}
```

- `requirement` is a provision ID from `assets/frameworks/gdpr.yaml` that applies to the engagement's roles.
- `summary` is printed as the statement on the compliance of the processing and the effectiveness of data protection. Write it in the auditor's voice: what is in place, how well it works, and where it falls short. Do not call it a legal opinion.
- `scope_appropriate` and `scope_note` are the conclusion on whether the audit scope and the stated roles fit the processing the organization carries out. A scope that leaves out processing the organization does (a second product, the processing it carries out as processor) without saying why is not appropriate.
- `management_response` stays `null` unless the organization provided its correction and corrective action; it prints in Section VI.
- Every string here is printed. It names no one but `management.name`, never a data subject, and contains no email address or phone number.
