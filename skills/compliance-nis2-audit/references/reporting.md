# Report, review packet and sign-off

## Build

```bash
python scripts/nis2.py validate <engagement> --final   # workpapers, QA, findings, entity description
python scripts/nis2.py render <engagement>
python scripts/nis2.py packet <engagement>
```

`render` writes to `report/`:

- `nis2-<type>-<entity>-DRAFT.pdf` until sign-off, then `nis2-<type>-<entity>.pdf`: an AI Audit with the content of an audit report under ISO 19011. The cover, header, footer and Section I say it is not an audit by a competent authority, not a security audit under Art. 32(2)(b) of the Directive or national law (such as § 61 BSIG), and not legal advice.
  - Section I, the audit report: audit details, objectives, scope with the entity's classification, method, summary of findings, implementation and effectiveness of the measures, the results for governance (Art. 20), risk management (Art. 21(1), 21(2)(f)) and reporting (Art. 23), appropriateness of the scope and classification, the conclusion, and the model's signature.
  - Section II, the entity's description of its scope and context (`context.yaml`).
  - Section III, the graded findings: requirement, statement, objective evidence.
  - Section IV, every requirement in scope with the units that address it, the procedures performed and the results, grouped as scope, governance, risk-management measures, reporting, registration and the Implementing Regulation annex.
  - Section V, applicability: every requirement of the catalog, whether it applies to the entity types in scope, why not when it does not, and the audit result.
  - Section VI, the entity's response to findings.
- `workpapers.xlsx`: units, samples, deviations, findings, applicability and the evidence register.
- `evidence-index.csv`: every artifact with its hash and the workpapers and findings that cite it.
- `report-data.json`: the exact data the PDF was built from.

Report text comes from `assets/report/text/<language>.yaml` (`en`, `de`; set by `language` in `engagement.yaml`) and the workpapers; requirement titles come from `assets/frameworks/nis2.yaml` and its German overlay; the layout is `scripts/engine/report.typ` and the logo `assets/report/logo.svg`. Replace the wording with your own reviewed templates by editing the YAML, and the logo by replacing the SVG. Neither requires code changes. The layout file is shared by every skill on the requirements engine and is not edited here.

## What the PDF may identify

The PDF names the entity, its suppliers, `management.name` and title, and the model that signed. It names no one else. It contains no email address and no phone number. `validate --final` enforces this on every string the PDF can contain, and `signoff` and `render` both run that check.

- Section IV prints the workpaper `statement` when it is set, otherwise the control title from `controls.csv`. The source description stored in `control` is not printed.
- Section II prints `context.yaml` at the engagement root. It prints `bundle/context.yaml` only when that file is `management-approved`. A connector draft is omitted, and the section says the description was not provided.
- The same check covers procedures, deviation descriptions, design rationales, scope limitations, sample notes, findings (statement, objective evidence, response), the summary and the scope note.
- `report/evidence-index.csv` and the Evidence sheet of `workpapers.xlsx` replace any email address, phone number or person's name with `[redacted]`. Files in `bundle/` are unchanged.
- The check treats two capitalized words followed by a parenthesis in `context.yaml` or a control description as a person introduced by name. "Implementing Regulation (EU) 2024/2690" trips it. Write "Regulation (EU) 2024/2690" or "the Implementing Regulation" in `context.yaml` and in printed workpaper text. If `validate --final` says a text "names" something that is not a person, reword the text; do not remove the check.

`review/packet.md` is the internal record. It quotes observations in full. Send the entity the PDF, not the packet and not the bundle.

## Sign-off

`review/packet.md` is the record of the conclusion, every finding, deviation, design gap and scope limitation, low- and medium-confidence conclusions, and auditor observations. Each entry links to the evidence files.

The model that ran the audit signs it:

```bash
python scripts/nis2.py signoff <engagement> --model "Grok 4.7"
python scripts/nis2.py render <engagement>
```

`signoff` re-validates everything and records the model name, today's date, and a digest of the workpapers, test plan, QA, findings, entity description and bundle manifest. `render` writes the AI Audit PDF without the draft watermark. Section I is signed:

```
Grok 4.7
AI Auditor
5 October 2026
Not an audit by a competent authority. Not legal advice.
```

Section I also names the entity's representative from `management.name` and `management.title`: the real person and role, taken from the evidence and written in `engagement.yaml` before sign-off. In Germany this is usually a member of the Geschäftsleitung. The report never prints a blank, a bracket, or a placeholder for a date, a name, or a title. Any later change to the work clears the signature and the next render is a draft again. Do not edit `signoff` by hand, and do not sign as an authority, an audit firm or a person.

## The entity's part

- **Scope, classification and context.** The entity owns them. The file readers see is `context.yaml` at the engagement root, written for the report and not copied from the connector draft. Put the approved version there with `status: management-approved`. The AI Audit can be signed before that; the report then says the description is not management-approved.
- **Responses to findings.** Record the entity's corrective measures in each finding's `management_response`; they print in Section VI. Art. 21(4) requires corrective measures without undue delay; this AI Audit only reports them and does not verify them.
- **Use of the report.** Tell the user the report cannot be submitted to a competent authority as proof of compliance, as a security audit under Art. 32(2)(b) or national law (in Germany, for example, an audit ordered under § 61 BSIG), or as a legal opinion.
