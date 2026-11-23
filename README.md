# compliance-skills

Agent skills for security and privacy compliance: get audit-ready for SOC 2, ISO 27001, GDPR and NIS2, then run an AI Audit against any of them: modeled on a SOC 2 examination, an ISO 27001 certification audit, or a GDPR or NIS2 compliance audit. Reports and framework text come in English and German.

Example AI Audit report: [DoneThat SOC 2 Type 1](https://trust.donethat.ai/en/documents/qE94tnY9AAEAGQAAAaD7eRKWtWoj5-GG).

The skills follow the open [Agent Skills](https://agentskills.io/specification) format, so they work in Claude Code, Codex, Gemini CLI, Cursor, GitHub Copilot and any other agent that reads `SKILL.md`. Every skill folder is self-contained, and deterministic work runs in plain Python, so nothing depends on one vendor's agent features.

## Skills

| Skill | Kind | What it does |
|---|---|---|
| [`compliance`](skills/compliance/SKILL.md) | hub | Picks the framework, the step and the language, and routes to the skills below |
| [`compliance-prep`](skills/compliance-prep/SKILL.md) | prep | Fills scope, system description, vendors, risks, policies, measures and evidence in Probo, Vanta, Drata or a git folder of records. Keeps records that state the same fact in agreement, runs readiness checks, and sets up a separate "Criteria, AI Audited" framework |
| [`compliance-soc2-audit`](skills/compliance-soc2-audit/SKILL.md) | audit | AI Audit modeled on a SOC 2 Type 1 or Type 2 examination, signed by the model that ran it |
| [`compliance-iso27001-audit`](skills/compliance-iso27001-audit/SKILL.md) | audit | AI Audit modeled on an ISO/IEC 27001:2022 Stage 1, Stage 2, surveillance or recertification audit |
| [`compliance-gdpr-audit`](skills/compliance-gdpr-audit/SKILL.md) | audit | AI Audit of GDPR compliance for the organization's roles (controller, processor): an assessment as of a date, or an audit of records over a period |
| [`compliance-nis2-audit`](skills/compliance-nis2-audit/SKILL.md) | audit | AI Audit of NIS2 compliance for an essential or important entity, including Implementing Regulation (EU) 2024/2690 for digital providers |

**Prep and audit stay separate on purpose.** Prep writes to the system of record. An audit reads a hashed snapshot of it and never changes it. Every audit skill reads the same sources: Probo, Vanta, Drata, an export folder, or the compliance-prep records folder directly (`--connector records`). Run the audit in a fresh context, ideally with a different model, so the one that prepared the records does not grade its own work.

## Frameworks

| Catalog | Covers | Prep | AI Audit |
|---|---|---|---|
| `soc2` | Trust Services Criteria 2017 (revised 2022): CC1–CC9, A1, C1, PI1, P1–P8 | yes | yes |
| `iso27001` | ISO/IEC 27001:2022 with Amd 1:2024: clauses 4–10, 93 Annex A controls | yes | yes |
| `gdpr` | Regulation (EU) 2016/679: 92 auditable controller and processor obligations, chapters II–V | yes | yes |
| `nis2` | Directive (EU) 2022/2555: scope (Art. 3, 26), governance, risk-management measures, reporting, registration (Art. 20–27), and Implementing Regulation (EU) 2024/2690; notes on German BSIG and Austrian NISG 2026 | yes | yes |

- **Where they live:** the catalogs live once in [`shared/frameworks/`](shared/frameworks), and German text in [`shared/frameworks/de/`](shared/frameworks/de).
- **Text only:** a translation changes only titles, summaries and evidence hints, never IDs or mappings, so the language never changes what is audited.
- **Paraphrases:** the summaries are paraphrases for navigation. The authoritative texts are the AICPA criteria, the ISO standard, and the EU legal texts on EUR-Lex. A licensed firm can add a `text:` field to any entry with the official wording, and the reports print it.

## Languages

Set `language: en` or `language: de` in an engagement (`init --language de`).

- **What changes:** the report wording, the criteria and requirement text, dates (`30. Juni 2026`), page size, and the workpaper spreadsheet headers.
- **What the agent must do:** write its own report text in the same language.
- **What stays English:** internal working files (review packet, rollup, coverage, request list) and the evidence index, so a reviewer can always read them.
- **Where the wording lives:** report wording is in each audit skill's `assets/report/text/<lang>.yaml`. A firm can replace it without touching code.

## Install

Copy or symlink the folders in `skills/` into your agent's skills directory. For Claude Code that is `~/.claude/skills/`:

```bash
git clone git@github.com:heychristoph/compliance-skills.git
ln -s "$PWD"/compliance-skills/skills/* ~/.claude/skills/
pip install -r compliance-skills/skills/compliance-soc2-audit/scripts/requirements.txt
```

You can also tell the agent to read `skills/compliance/SKILL.md`. Each skill lists its own Python requirements in `scripts/requirements.txt`.

## Quick start

```bash
# Get ready (from the folder that holds prep.yaml)
python skills/compliance-prep/scripts/prep.py check

# Audit, in a fresh session
python skills/compliance-soc2-audit/scripts/soc2.py init ./acme-2026 --type 2 --start 2026-01-01 --end 2026-06-30 \
  --org "Acme GmbH" --system "Acme Platform" --categories security,availability,confidentiality \
  --language de --connector probo --option organization_id=<id>
export PROBO_TOKEN=...
```

Then ask your agent: *"Run the AI Audit in ./acme-2026."* `soc2.py status ./acme-2026` shows progress and the next step at any time.

## Repository layout

```
skills/                       one self-contained folder per skill (what agents install)
├── compliance/               hub
├── compliance-prep/          prep: scripts/prep.py, write-capable connectors (Probo, Vanta, Drata, folder)
├── compliance-soc2-audit/    SOC 2 opinion engine (scripts/) on the shared library
├── compliance-iso27001-audit/   assets/profile.yaml + report text; engine copied in
├── compliance-gdpr-audit/       "
└── compliance-nis2-audit/       "
shared/                       single source for files several skills need
├── frameworks/               soc2, iso27001, gdpr, nis2 catalogs; de/ translations
├── lib/                      -> scripts/common/: IO, languages, catalogs and ID finders, bundle writer,
│                                audit connectors (probo, vanta, drata, folder, records), manifest schema
└── engines/requirements/     -> scripts/engine/: the requirements audit engine (check, plan, sample,
                                 validate, findings, render) used by the ISO 27001, GDPR and NIS2 skills
tools/sync.py                 copies shared/ into each skill; --check fails on a stale copy
evals/<framework>/            synthetic engagements, oracle, graders, Probo mock
tests/                   prep rules, catalogs, translations, sync
```

**Edit `shared/`, then run `python tools/sync.py`.** The copies under `skills/*/assets/frameworks/`, `skills/*/scripts/common/` and `skills/*/scripts/engine/` are generated: never edit them, and commit them with their source. Each skill must work when it is installed alone.

## Design guidelines

1. **One contract per step: files.** All state is files described by JSON Schemas, so any step can be rerun or resumed by any agent.
2. **Vendor names stay in the connectors, framework specifics in data.** A new source is one module in `shared/lib/connectors/`. A new requirements framework is a catalog, a `profile.yaml` and report text, with no engine code.
3. **Scripts count, agents judge.** Hashing, sampling, validation and report text are code. Evidence inspection, design evaluation and the opinion are the agent's.
4. **No conclusion without evidence.** Every pass cites hashed artifacts, and the validator rejects anything uncited.
5. **The report is rendered, never written.** Report text comes from the text files plus the workpapers, so the PDF cannot disagree with the work.
6. **Evals before claims.** Synthetic engagements with planted defects measure what an agent and model actually catch.

## Development

```bash
python tools/sync.py --check
python -m unittest discover -s tests
python evals/soc2/make_fixture.py && python evals/soc2/run.py --case type2 --agent oracle
python evals/soc2/run.py --case type2 --agent oracle --language de
python evals/iso27001/make_fixture.py && python evals/iso27001/run.py --case stage2 --agent oracle
python evals/gdpr/make_fixture.py && python evals/gdpr/run.py --case audit --agent oracle
python evals/nis2/make_fixture.py && python evals/nis2/run.py --case audit --agent oracle
python evals/soc2/test_probo_connector.py && python evals/iso27001/test_probo_connector.py
```

## Status

- **Tested:**
  - Every audit pipeline with the oracle on synthetic fixtures with planted defects (score 1.0), in English and German: SOC 2 (Type 1, Type 2), ISO 27001 (Stage 1, Stage 2), GDPR (assessment, audit) and NIS2 (assessment, audit).
  - English SOC 2 and ISO 27001 report data is identical to the earlier separate repos.
  - All four audits against a Probo mock; the records connector on the prep folder template; prep rules on the folder template; prep against a self-hosted Probo v0.297.
- **Not yet tested:**
  - Vanta and Drata against live accounts (the Drata framework tags for GDPR and NIS2 are guesses; set `framework_tag`).
  - A full run by a real agent on the fixtures.
- **Known gap:** the audit Probo connector uses the MCP tool names from before Probo v0.304, which renamed measures to internal controls. The prep connector handles the rename; the audit connector needs the new tool names checked against a live v0.304+ instance.
- **Not included yet:**
  - Shared connector code between prep (which writes) and the audits (which only read).
  - SOC 3, bridge letters, the inclusive subservice method, ISO multi-site sampling and audit time calculation, and national NIS2 law as audit criteria (national rules are noted, not graded).

## Professional responsibility

These skills produce AI Audits and readiness work.

- An AI Audit is not an official SOC 2 audit, an AICPA attestation, an ISO/IEC 27001 certification, a GDPR certification (Art. 42), an audit or decision of a data protection supervisory authority or NIS2 competent authority, or legal advice.
- No CPA firm or accredited certification body issues it. The model that ran the work signs it, and the report says so.
- The prep skill does not replace an auditor or legal advice.

## Predecessors

This repository replaces [security-audit-prep](https://github.com/heychristoph/security-audit-prep), [soc2-auditor](https://github.com/heychristoph/soc2-auditor) and [iso27001-auditor](https://github.com/heychristoph/iso27001-auditor).

## License

MIT
