# Report, review packet and sign-off

## Build

```bash
python scripts/gdpr.py validate <engagement> --final   # workpapers, QA, findings, processing context
python scripts/gdpr.py render <engagement>
python scripts/gdpr.py packet <engagement>
```

`render` writes to `report/`:

- `gdpr-<type>-<org>-DRAFT.pdf` until sign-off, then `gdpr-<type>-<org>.pdf`: an AI Audit in the shape of a management system audit report (ISO 19011:2018, 6.5.1), with the GDPR as the criteria. The cover, header, footer and Section I say it is not a supervisory authority audit, not a certification under Art. 42 and not legal advice.
  - Section I, the audit report: audit details, objectives, scope and roles, method, summary of findings, the statement on the compliance of the processing and the effectiveness of data protection, a result for accountability (Art. 5(2), Art. 24), the records of processing (Art. 30), security of processing (Art. 32) and personal data breaches (Art. 33 and 34), appropriateness of the scope, the conclusion (compliant, compliant with corrective actions, not compliant, or no conclusion), and the model's signature.
  - Section II, the organization's description of the processing in scope and its context (`context.yaml`).
  - Section III, the graded findings: provision, statement, objective evidence.
  - Section IV, every obligation in scope, grouped by chapter, with the units that address it, the procedures performed and the results.
  - Section V, the applicability of every obligation in the catalog: whether it applies to the organization's roles, the reason when it does not (it binds only other roles, or it is an optional code of conduct or certification mechanism), and the audit result.
  - Section VI, the organization's response to findings.
- `workpapers.xlsx`: units, samples, deviations, findings, the applicability of each obligation and the evidence register.
- `evidence-index.csv`: every artifact with its hash and the workpapers and findings that cite it.
- `report-data.json`: the exact data the PDF was built from.

Report text comes from `assets/report/text/<language>.yaml` (`en`, `de`; set by `language` in `engagement.yaml`), the provision titles from `assets/frameworks/gdpr.yaml` and `assets/frameworks/de/gdpr.yaml`, and everything else from the workpapers, findings and `context.yaml`. Replace the wording with your own reviewed templates by editing the YAML, and the logo by replacing `assets/report/logo.svg`. Neither requires code changes. Keep every disclaimer: the report must never read as a certification, a supervisory authority finding or legal advice.

## What the PDF may identify

The PDF names the organization, its processors and suppliers, `management.name` and title, and the model that signed. It names no one else: no employee, no data subject, no supplier's contact. It contains no email address and no phone number. `validate --final` enforces this on every string the PDF can contain, and `signoff` and `render` both run that check.

- Section IV prints the workpaper `statement` when it is set, otherwise the control title from `controls.csv`. The source description stored in `control` is not printed.
- Section II prints `context.yaml` at the engagement root. It prints `bundle/context.yaml` only when that file is `management-approved`. A connector draft is omitted, and the section says the description was not provided.
- The same check covers procedures, deviation descriptions, design rationales, scope limitations, sample notes, findings (statement, objective evidence, response), the summary and the scope note.
- `report/evidence-index.csv` and the Evidence sheet of `workpapers.xlsx` print artifact titles and paths with any email address, phone number or person's name replaced by `[redacted]`. Files in `bundle/` are unchanged.

`review/packet.md` is the internal record. It quotes observations in full. Send the organization the PDF, not the packet and not the bundle.

## Sign-off

`review/packet.md` is the record of the conclusion, every finding, deviation, design gap and scope limitation, low- and medium-confidence conclusions, and auditor observations. Each entry links to the evidence files.

The model that ran the audit signs it:

```bash
python scripts/gdpr.py signoff <engagement> --model "<model that ran this audit>"
python scripts/gdpr.py render <engagement>
```

`signoff` re-validates everything and records the model name, today's date, and a digest of the workpapers, test plan, QA, findings, processing context and bundle manifest. `render` writes the AI Audit PDF without the draft watermark. Section I is signed:

```
<model name>
AI Auditor
5 October 2026
Not a GDPR certification. Not legal advice.
```

Section I also names the organization's representative from `management.name` and `management.title`: the real person and role, taken from the evidence and written in `engagement.yaml` before sign-off. The report never prints a blank, a bracket, or a placeholder for a date, a name, or a title. Any later change to the work clears the signature and the next render is a draft again. Do not edit `signoff` by hand, and do not sign as a supervisory authority, a certification body, a data protection officer or a person.

## The organization's part

- **Processing scope and context.** The organization owns them. The file readers see is `context.yaml` at the engagement root, written for the report and not copied from the connector draft. Put the approved version there with `status: management-approved`. The AI Audit can be signed before that; the report then says the description is not management-approved.
- **Roles.** The organization's roles as controller and processor are a fact about its processing, shown by its contracts and records of processing. Section V prints the result of `roles`; if the organization disputes a role, resolve it before sign-off.
- **Responses to findings.** Record the organization's correction and corrective action in each finding's `management_response`; they print in Section VI. This AI Audit only reports them; it does not verify them, and it does not advise on notifying a supervisory authority or data subjects.
