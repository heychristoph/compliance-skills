# Report, annexes, fix list and sign-off

## Build

```bash
python scripts/app.py validate <engagement> --final   # workpapers, QA, findings, context, privacy
python scripts/app.py signoff <engagement> --model "<model that did the assessment>"
python scripts/app.py render <engagement>
python scripts/app.py packet <engagement>
```

`render` writes to `report/`:

- `app-assessment-assessment-<org>-DRAFT.pdf` until sign-off, then `app-assessment-assessment-<org>.pdf`: the AI assessment. The cover, header, footer and Section I say it is not a penetration test, not a certification, not an authority audit and not legal advice.
  - **Section I**, the assessment report: details, objectives, scope and role, method, the summary of findings with the **evidence-strength summary**, the statement on the security and data processing of the application (`summary`), results for access control, data processing and sub-processors, appropriateness of the scope, scope limitations, the conclusion, and the model's signature.
  - **Section II**, the description of the application (`context.yaml`).
  - **Section III**, the graded findings: requirement, statement, objective evidence.
  - **Section IV**, every requirement in scope, grouped (access control, authentication, data protection, code, operations, inventory, sub-processors, retention, incidents, AI), with the **crosswalk** to GDPR and NIS2, the units, the procedures and the results.
  - **Section V**, the applicability of every requirement: whether it applies to the role and to the features the app uses, the reason when it does not, and the result.
  - **Section VI**, the organization's response to findings.
  - **Annex A**, the technical and organizational measures; **Annex B**, the sub-processors.
- `annex-measures.md` and `annex-subprocessors.md`: Annex A and B as editable Markdown, in the report language.
- `fixes.md`: the fix list for the developer.
- `workpapers.xlsx`, `evidence-index.csv`, `report-data.json`: the units, samples, deviations, findings, applicability and evidence register; the artifacts with hashes and who cites them; the data the PDF was built from.

Report text comes from `assets/report/text/<language>.yaml` (`en`, `de`), requirement titles from `assets/frameworks/app.yaml` and `assets/frameworks/de/app.yaml`, and everything else from the workpapers, findings, `context.yaml` and `review/stack.yaml`. Edit the YAML to change wording and replace `assets/report/logo.svg` for the logo; neither needs code changes. Keep every disclaimer.

## Evidence-strength summary

Section I states how each requirement in scope was verified, by the strongest evidence tier its units cite: from the code itself (`direct`), from live configuration read through read-only tools (`captured`), from documents and screenshots the organization provided (`client`), from answers only (`inquiry`, not verified), or not assessed. It is computed from the `obtained` field of the cited artifacts. If it looks weak, get better evidence; do not reword it.

## Crosswalk

Each row of Section IV shows the GDPR and NIS2 provisions the requirement supports (from `maps` in the catalog, for example "GDPR Art.32(1)(b), Art.25(1) · NIS2 Art.21(2)(i), IR.11.1"). A mapping marks a real relationship, not equivalence: meeting SEC-AC-01 supports Art. 32 GDPR; it does not show compliance with it. NIS2 mappings point to obligations of the client, as an essential or important entity, that a supplier's application supports (supply chain security, Art. 21(2)(d), and the measures of Art. 21(2)).

## Annexes

**Annex A, technical and organizational measures** (`annex-measures.md`). One row per security requirement (SEC-*) in scope: the requirement, the measure, the result of this assessment, and how it was verified (the evidence tier). It is meant to be attached to the DPA as the measures annex (Art. 28(3)(c), Art. 32 GDPR). Rows whose result is a finding, "not verified" or "not audited" are not verified measures. Tell the user to attach only the rows verified as in place, or to fix the rest and assess again; the editable Markdown makes that possible without changing the PDF.

**Annex B, sub-processors** (`annex-subprocessors.md`). Every service found in the code and configuration (`subprocessors` in `review/stack.yaml`: recipe components and the services the code scan found) and in `outsourced` in `context.yaml`, with the service and a link to the provider's DPA where the recipe knows it. The controller (the client) must authorize sub-processors before they are used (Art. 28(2) GDPR). A service listed here that does not process personal data (a font CDN, say) can be removed from the copy attached to the DPA; say why in the cover message.

## Fix list

`fixes.md` lists the findings for the developer, major weaknesses first, then minor ones, then opportunities for improvement, each with its ID, requirement and statement, followed by the units that rest only on answers, for which evidence should be provided. It does not contain the fix: that is worked out in a separate session after the report. When the user wants to fix things, start a new session (or tell them to), work from `fixes.md` in the repository, and assess again afterwards in a new engagement folder.

## What the PDF may identify

The PDF names the organization, its client, its sub-processors and suppliers, `management.name` and title, and the model that signed. It names no one else: no employee, no end user of the app, no supplier's contact. It contains no email address, no phone number and no secret. `validate --final` enforces names and contact details on every string the PDF can contain, and `signoff` and `render` both run that check; secrets are your responsibility.

- Section IV prints the workpaper `statement` when it is set, otherwise the requirement title.
- Section II prints `context.yaml` at the engagement root.
- `report/evidence-index.csv` and the Evidence sheet of `workpapers.xlsx` print artifact titles and paths with any email address, phone number or person's name replaced by `[redacted]`. Files in `bundle/` and `intake/` are unchanged.

`review/packet.md` is the internal record. It quotes observations in full. Send the client the PDF and the annexes, not the packet, the bundle or `intake/`.

## Sign-off

The model that ran the assessment signs it:

```bash
python scripts/app.py signoff <engagement> --model "<model that did the assessment>"
python scripts/app.py render <engagement>
```

`signoff` re-validates everything and records the model name, today's date, and a digest of the workpapers, test plan, QA, findings, context and bundle manifest. Section I is signed with the model name, the title AI Auditor and the date. It also names the organization's representative from `management.name` and `management.title`: the real person and role, never a placeholder. Any later change clears the signature, and the next render is a draft again. Do not edit `signoff` by hand, and do not sign as a person, a penetration tester, a certification body or an authority.

## The organization's part

- **Description.** The organization owns `context.yaml`. Set `status: management-approved` once the user has confirmed it. The assessment can be signed before that; the report then says the description is not approved.
- **Role.** Whether the organization runs production for the client is a fact shown by the accounts, contracts and access. Section V prints the result of `roles`; resolve any dispute before sign-off.
- **Responses to findings.** Record a correction the organization made or plans in each finding's `management_response`; it prints in Section VI. This assessment reports it but does not verify it. To verify a fix, assess again.
