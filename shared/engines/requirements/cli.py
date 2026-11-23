#!/usr/bin/env python3
"""The deterministic half of an AI Audit against a requirements catalog (ISO/IEC 27001, GDPR, NIS2).

Each audit skill runs this through its own command (iso27001.py, gdpr.py, nis2.py),
which sets the framework profile. The report is an AI Audit, not a certification,
a supervisory authority's assessment or an official audit.

Run `<command> status <engagement>` at any time; it prints the next step.

  init      create engagement.yaml
  ingest    pull evidence through the configured connector into bundle/
  check     verify bundle integrity, applicability and coverage
  plan      create or refresh testplan.csv
  sample    draw seeded samples and write workpaper skeletons
  validate  check workpapers (add --final for findings, QA and the description)
  qa        record an independent review of one workpaper
  rollup    summarize results by requirement and list deviations to grade
  packet    write the review packet
  render    build the AI Audit PDF, workpaper spreadsheet and evidence index
  signoff   sign the AI Audit with the model that ran it
  status    show progress and the next step
"""

from __future__ import annotations

import argparse
import datetime as dt
import secrets
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402
import planning  # noqa: E402
import review  # noqa: E402
from common import connectors  # noqa: E402
from common.bundle import BundleWriter  # noqa: E402
from core import APPLICABILITY, AUDIT_TYPES, CLI, PROFILE, AuditError, Engagement, dump_yaml, load_json  # noqa: E402

NOT_CERT = f"This is an AI Audit. {PROFILE['not_official']}"


def cmd_init(a) -> int:
    root = Path(a.engagement)
    if (root / "engagement.yaml").exists():
        raise AuditError(f"{root}/engagement.yaml already exists.")
    cfg = {
        "schema_version": 1,
        "organization": a.org,
        "scope": a.scope,
        "auditor": "AI Audit",
        "audit_type": a.type,
        "language": a.language,
    }
    scope = APPLICABILITY.get("scope")
    if scope:
        values = [x.strip() for x in (getattr(a, scope["config"]) or "").split(",") if x.strip()]
        cfg[scope["config"]] = values
    if PROFILE["audit_types"][a.type].get("as_of"):
        if not a.as_of:
            raise AuditError(f"A {a.type} audit needs --as-of (the date of the documentation review).")
        cfg["as_of"] = a.as_of
    else:
        if not (a.start and a.end):
            raise AuditError(f"A {a.type} audit needs --start and --end (the period whose records are sampled).")
        cfg["period"] = {"start": a.start, "end": a.end}
    options = dict(o.split("=", 1) for o in a.option or [])
    cfg["source"] = {"connector": a.connector, "options": options}
    cfg["sampling_seed"] = secrets.randbelow(10**9)
    cfg["signoff"] = None
    dump_yaml(cfg, root / "engagement.yaml")
    Engagement(root).config  # validate
    print(f"Created {root}/engagement.yaml (sampling seed {cfg['sampling_seed']}). {NOT_CERT} Run ingest next.")
    return 0


def cmd_ingest(a) -> int:
    eng = Engagement(a.engagement)
    src = eng.config["source"]
    if eng.bundle.exists():
        if not a.replace:
            raise AuditError("bundle/ already exists. Evidence is collected once per engagement; use --replace to pull again "
                             "(the old bundle is kept as bundle.replaced-<timestamp>).")
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.move(str(eng.bundle), str(eng.root / f"bundle.replaced-{stamp}"))
    writer = BundleWriter(eng.bundle, src["connector"], framework=eng.framework)
    connectors.load(src["connector"]).pull(writer, src.get("options") or {}, eng)
    manifest = writer.finish()
    kinds = {}
    for art in manifest["artifacts"]:
        kinds[art["kind"]] = kinds.get(art["kind"], 0) + 1
    print(f"Ingested {len(manifest['artifacts'])} artifacts via {src['connector']}: " + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))
    if eng.workpaper_files():
        print("warning: workpapers already exist and may cite artifact IDs from the previous bundle; run validate.")
    return 0


def cmd_check(a) -> int:
    eng = Engagement(a.engagement)
    errors, warnings = checks.run(eng)
    return _report(errors, warnings, ok="Bundle intact. See review/coverage.md and review/requests.csv.")


def cmd_plan(a) -> int:
    eng = Engagement(a.engagement)
    todo = planning.plan(eng)
    print(f"Wrote {eng.testplan_path}.")
    if todo:
        print("Complete these rows (see references/planning.md), then run sample:")
        for t in todo:
            print(f"  - {t}")
        return 1
    print("All rows complete. Review them (including the catalog defaults on REQ- rows), then run sample.")
    return 0


def cmd_sample(a) -> int:
    eng = Engagement(a.engagement)
    log = planning.sample(eng, force=a.force)
    for line in log:
        print(f"  {line}")
    written = [line for line in log if not line.startswith("warning:")]
    print(f"{len(written)} workpaper changes in {eng.workpapers}." if written else "Workpapers already match the test plan.")
    return 0


def cmd_validate(a) -> int:
    eng = Engagement(a.engagement)
    errors, warnings = review.validate(eng, final=a.final)
    return _report(errors, warnings, ok="All checks passed." if a.final else "Workpapers valid.")


def cmd_qa(a) -> int:
    eng = Engagement(a.engagement)
    review.record_qa(eng, a.control, a.verdict, a.issue or [], a.checked or [], a.by)
    print(f"Recorded QA {a.verdict} for {a.control}.")
    return 0


def cmd_rollup(a) -> int:
    print(review.rollup(Engagement(a.engagement)))
    return 0


def cmd_packet(a) -> int:
    eng = Engagement(a.engagement)
    review.packet(eng)
    print(f"Wrote {eng.review / 'packet.md'}.")
    return 0


def cmd_render(a) -> int:
    from render import render

    out = render(Engagement(a.engagement))
    for w in out["warnings"]:
        print(f"warning: {w}")
    print(f"{'Signed AI Audit' if out['final'] else 'DRAFT AI Audit'} report: {out['pdf']}")
    print(NOT_CERT)
    print(f"Workpapers: {out['xlsx']}\nEvidence index: {out['evidence_index']}")
    return 0


def cmd_signoff(a) -> int:
    eng = Engagement(a.engagement)
    digest = review.signoff(eng, a.model)
    print(f"Signed by {a.model.strip()} (digest {digest[:16]}). Run render to produce the AI Audit PDF.")
    print(NOT_CERT)
    return 0


def cmd_status(a) -> int:
    root = Path(a.engagement)
    eng = Engagement(root)
    if not eng.config_path.exists():
        return _next("No engagement yet.", f"{CLI} init {root} --org ... (see references/engagement-folder.md)")
    eng.config
    if not eng.manifest_path.exists():
        return _next(f"{AUDIT_TYPES[eng.audit_type]} audit configured, no evidence yet.", f"{CLI} ingest {root}")
    if not (eng.review / "coverage.md").exists():
        return _next("Evidence ingested, not checked.", f"{CLI} check {root}")
    if not eng.testplan_path.exists():
        return _next("Bundle checked, no test plan.", f"{CLI} plan {root}")
    rows = eng.testplan()
    included = [r for r in rows if r.get("include", "yes").lower() != "no"]
    incomplete = [r["control_id"] for r in included if not r["frequency"] or not r["nature"]]
    if incomplete:
        return _next(f"Test plan has {len(incomplete)} incomplete rows: {', '.join(incomplete[:10])}",
                     f"fill frequency and nature in testplan.csv (references/planning.md), then {CLI} sample")
    wps = eng.load_workpapers()
    if len(set(wps) & {r["control_id"] for r in included}) < len(included):
        return _next(f"{len(included) - len(wps)} units have no workpaper.", f"{CLI} sample {root}")
    pending = sorted(cid for cid, wp in wps.items() if wp.get("conclusion") == "pending")
    if pending:
        return _next(f"{len(wps) - len(pending)} of {len(wps)} units audited. Pending: {', '.join(pending[:15])}{' ...' if len(pending) > 15 else ''}",
                     f"audit each pending unit (references/control-testing.md), then {CLI} validate")
    errors, _ = review.validate(eng)
    if errors:
        return _next(f"All units audited; {len(errors)} validation errors.", f"{CLI} validate {root}, fix, repeat")
    qa = load_json(eng.qa_path) if eng.qa_path.exists() else {"reviews": []}
    reviewed = {r["control_id"] for r in qa["reviews"]}
    if len(reviewed & set(wps)) < len(wps):
        return _next(f"QA reviewed {len(reviewed & set(wps))} of {len(wps)} workpapers.", "QA review (references/qa-review.md)")
    if not eng.findings_path.exists():
        return _next("Auditing and QA done, no findings yet.", f"{CLI} rollup {root}, then write findings.json (references/evaluating.md)")
    errors, _ = review.validate(eng, final=True)
    if errors:
        return _next(f"{len(errors)} final validation errors.", f"{CLI} validate {root} --final, fix, repeat")
    pdfs = sorted(eng.report.glob("*.pdf")) if eng.report.exists() else []
    if review.signed_off(eng):
        final_pdfs = [p for p in pdfs if not p.stem.endswith("-DRAFT")]
        if final_pdfs:
            return _next(f"Complete. AI Audit report: {final_pdfs[-1]}", "none")
        return _next("Signed; AI Audit PDF not rendered.", f"{CLI} render {root}")
    return _next("Ready to sign.", f"{CLI} signoff {root} --model \"<model that ran this audit>\" && {CLI} render {root} && {CLI} packet {root}")


def _next(state: str, step: str) -> int:
    print(f"State: {state}\nNext:  {step}")
    return 0


def _report(errors: list[str], warnings: list[str], ok: str) -> int:
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"{len(errors)} errors, {len(warnings)} warnings.")
        return 1
    print(f"{ok} ({len(warnings)} warnings)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog=CLI, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create engagement.yaml")
    s.add_argument("engagement")
    s.add_argument("--org", required=True, help="legal name of the organization")
    s.add_argument("--scope", required=True, help=PROFILE.get("scope_help", "scope statement, as the report prints it"))
    s.add_argument("--type", required=True, choices=list(AUDIT_TYPES), help="audit type")
    s.add_argument("--language", default="en", choices=["en", "de"], help="language of the report (default en)")
    scope = APPLICABILITY.get("scope")
    if scope:
        s.add_argument(f"--{scope['config'].replace('_', '-')}", dest=scope["config"], required=True,
                       help=f"comma-separated: {', '.join(scope['choices'])} ({scope.get('help', 'scope of this engagement')})")
    periodic = [k for k, v in PROFILE["audit_types"].items() if not v.get("as_of")]
    point = [k for k, v in PROFILE["audit_types"].items() if v.get("as_of")]
    s.add_argument("--start", help=f"start of the records period ({', '.join(periodic)})")
    s.add_argument("--end", help="end of the records period")
    s.add_argument("--as-of", help=f"date of the documentation review ({', '.join(point)})")
    s.add_argument("--connector", required=True, choices=connectors.available())
    s.add_argument("--option", action="append", help="connector option key=value (repeatable)")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("ingest", help="pull evidence into bundle/")
    s.add_argument("engagement")
    s.add_argument("--replace", action="store_true", help="pull again, keeping the old bundle aside")
    s.set_defaults(fn=cmd_ingest)

    for name, fn, help_ in [("check", cmd_check, "bundle integrity, applicability and coverage"), ("plan", cmd_plan, "create testplan.csv"),
                            ("rollup", cmd_rollup, "requirement summary"), ("packet", cmd_packet, "review packet"),
                            ("render", cmd_render, "build the report"), ("status", cmd_status, "progress and next step")]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("engagement")
        s.set_defaults(fn=fn)

    s = sub.add_parser("sample", help="draw samples, write workpaper skeletons")
    s.add_argument("engagement")
    s.add_argument("--force", action="store_true", help="overwrite or remove workpapers whose plan changed")
    s.set_defaults(fn=cmd_sample)

    s = sub.add_parser("validate", help="check workpapers")
    s.add_argument("engagement")
    s.add_argument("--final", action="store_true", help="also check findings, QA and the description")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("qa", help="record a QA review of one workpaper")
    s.add_argument("engagement")
    s.add_argument("control")
    s.add_argument("--verdict", required=True, choices=["agree", "disagree"])
    s.add_argument("--issue", action="append", help="what is wrong (repeatable; required for disagree)")
    s.add_argument("--checked", nargs="*", help="artifact IDs the reviewer opened")
    s.add_argument("--by", required=True, help="reviewing agent and model")
    s.set_defaults(fn=cmd_qa)

    s = sub.add_parser("signoff", help="sign the AI Audit with the model that ran it")
    s.add_argument("engagement")
    s.add_argument("--model", required=True, help="model name that performed the audit, as printed on the report")
    s.set_defaults(fn=cmd_signoff)

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except AuditError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
