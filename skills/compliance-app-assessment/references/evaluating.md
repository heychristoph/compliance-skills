# Grading findings and concluding

Run `python scripts/app.py rollup <engagement>` to see each requirement with its units and conclusions, every deviation still to grade, the units supported only by answers, and the requirements out of scope for the role (`review/rollup.md`). Check that list: a requirement excluded by role must really belong to the other party, and an optional one must really be unused. Then group the deviations into findings, grade each one, and write `findings.json`.

## From deviations to findings

A deviation is a fact in one workpaper. A finding is your judgment about a requirement. One finding can grade several deviations (RLS off on three tables is one finding against SEC-AC-01), and one deviation belongs only to the finding that best describes it.

Each finding is recorded against **one** requirement, the one that is not met, with:
- a **statement** of the weakness: the requirement and what is not met;
- the **objective evidence**: tables, buckets, files and lines, settings, documents, specific enough that the developer can find it;
- links to the workpaper **deviations** it grades, and the **evidence** artifact IDs.

The statement says what is wrong, not how to fix it. The fix is worked out in a separate session after the report, from `fixes.md`, by someone who can change the system. Do not assess fines, liability, or whether a breach must now be notified; that is legal advice.

Every deviation must be graded, and every `design-gap` must be a major or minor weakness. `validate --final` checks both.

## Grades

| Grade | ID | When |
|---|---|---|
| `major` | `NC-01` | A protection the app needs is missing or broken, so personal data are exposed or can be changed by people who should not have access; or a contract or safeguard the GDPR requires for personal data is missing. Typical: RLS off on a table with personal data that the client API can reach (SEC-AC-01); a policy with an always-true condition on personal data (SEC-AC-02); a service-role key or other privileged secret in frontend code or the repository (SEC-CODE-01, SEC-CODE-02); a public bucket with personal data (SEC-AC-06); a server function that returns or changes personal data without checking the caller (SEC-AC-04); authorization only in the browser, with nothing on the server or in the database behind it (SEC-AC-03); no DPA with a sub-processor that processes personal data, including an AI provider (DP-SUP-03, DP-AI-03); no DPA with the client while processing for it (DP-SUP-05); a regular transfer outside the EEA with no mechanism (DP-SUP-04); no backups of production (SEC-OPS-01); an AI builder or coding assistant with access to production personal data the client was not told about (DP-AI-08); special categories processed and not identified (DP-INV-01); several minor weaknesses against one requirement that together show it is not met. |
| `minor` | `NC-02` | A requirement is not met, but the main protection is in place and works, or the gap is limited in reach: admin MFA available but not enforced (SEC-AUTH-04); a role check in the browser while the database still enforces access (SEC-AC-03); an AI API called from the browser without server-side limits (DP-AI-05); email confirmation off (SEC-AUTH-01); a weak password policy (SEC-AUTH-02); no rate limits on sign-in (SEC-AUTH-03); wildcard redirect URLs (SEC-AUTH-07); one former team member still with access (SEC-AC-07); a high-severity dependency vulnerability not reachable from outside (SEC-CODE-03); a sub-processor missing from the list given to the client (DP-SUP-02); no documented retention period for one category (DP-LIFE-01). |
| `ofi` | `OFI-01` | The requirement is met, but something could be better: daily backups that meet the agreed recovery point without point-in-time recovery; leaked-password protection off with an otherwise strong policy. For a deviation, only when the requirement is still met; say why in the statement. |

When unsure between two grades, choose the more serious one and explain the judgment in the statement.

For each requirement with deviations, weigh:
- **Exposure.** Can someone outside the intended group read or change the data: anyone on the internet (anonymous key), any signed-in user, only team members?
- **Data.** Does it hold personal data, and of what kind? Health, ID documents, financial or children's data raise the grade.
- **Reach.** One table or all of them; one bucket of avatars or the bucket of ID scans; one admin or every user.
- **Compensating protection.** A browser-side check with RLS behind it is a smaller gap than one with nothing behind it. Check that the compensating protection really exists in the evidence; do not assume it.
- **Contract.** For data processing requirements: is personal data actually flowing to the party without the contract or safeguard?

## The conclusion

| `recommendation` | When | Printed |
|---|---|---|
| `recommended` | No weaknesses and no scope limitations. OFIs are allowed. | No significant weaknesses found as of the assessment date. |
| `recommended-with-actions` | Minor weaknesses only, or requirements not verified (scope limitations), and no major weakness. | Minor weaknesses to fix: the minor weaknesses need fixing and the unverified requirements need evidence. |
| `not-recommended` | At least one major weakness. | Significant weaknesses to fix: the major weaknesses must be fixed before the application is relied on for the personal data it processes, and the fixes should be verified by a new assessment. |
| `no-conclusion` | Scope limitations so significant that no conclusion can be formed. | No conclusion. |

`validate --final` checks that the recommendation follows from the grades.

## Scope limitations

`scope_limitations` lists, in the report language, what this assessment could not verify. It must not be empty when any unit is `inquiry-only` or `not-audited`; `validate --final` enforces it for `inquiry-only`. Name the requirements and what was missing:

- "SEC-OPS-02, DP-LIFE-02 and DP-INC-02 rest only on the organization's answers and were not verified."
- "No access to the Vercel project was available and no export was provided, so SEC-OPS-05 could not be assessed."

## findings.json

```json
{
  "schema_version": 1,
  "findings": [
    {
      "id": "NC-01",
      "grade": "major",
      "requirement": "SEC-AC-01",
      "statement": "Row-level security is not enabled on every table that the client API can reach.",
      "objective_evidence": "The row-level security query of 23 November 2026 shows RLS disabled on table treatment_notes, which the client reads in src/pages/Notes.tsx and which holds patients' treatment notes; the Supabase security advisor reports rls_disabled_in_public for the same table.",
      "deviations": [{"control": "REQ-SEC-AC-01", "item": "instance-1"}],
      "evidence": ["EV-0007", "EV-0006"],
      "management_response": null
    },
    {
      "id": "NC-02",
      "grade": "minor",
      "requirement": "SEC-AUTH-04",
      "statement": "Multi-factor authentication is not enforced for the app's administrators.",
      "objective_evidence": "The Multi-Factor settings export shows TOTP enabled but optional; the admin policies in the migrations do not check the authentication assurance level (aal2).",
      "deviations": [{"control": "REQ-SEC-AUTH-04", "item": "instance-1"}],
      "evidence": ["EV-0018"],
      "management_response": null
    }
  ],
  "scope_limitations": ["SEC-OPS-02, DP-LIFE-02 and DP-INC-02 rest only on the organization's answers and were not verified."],
  "recommendation": "not-recommended",
  "summary": "The app is built on Supabase with row-level policies on most tables, server-side AI calls for summaries and EU hosting. The major weaknesses in Section III expose personal data: a table of treatment notes without row-level security and a service-role key in the browser code.",
  "scope_appropriate": true,
  "scope_note": "",
  "prepared_by": "<agent / model>"
}
```

- `requirement` is a requirement ID from `assets/frameworks/app.yaml` that is in scope.
- `summary` is printed as the statement on the security and data processing of the application. Write it in the assessor's voice: what is in place, how well it works, and where it falls short. Mention GDPR or NIS2 only as the frameworks the requirements support, never as a compliance verdict.
- `scope_appropriate` and `scope_note`: does the assessed scope and role fit the application? A role of `developer` while the evidence shows the developer still has production access, or a repository that leaves out the backend without saying so, is not appropriate.
- `management_response` stays `null` unless the organization provided its correction; it prints in Section VI.
- Every string here is printed. It names no one but `management.name`, contains no email address, phone number or secret value.
