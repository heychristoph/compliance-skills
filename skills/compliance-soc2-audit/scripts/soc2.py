#!/usr/bin/env python3
"""soc2.py: the deterministic half of an AI Audit modeled on a SOC 2 examination.

The report is an AI Audit. It is not an official SOC 2 audit.

Run `soc2.py status <engagement>` at any time; it prints the next step.

  init      create engagement.yaml
  ingest    pull evidence through the configured connector into bundle/
  check     verify bundle integrity and criterion coverage
  plan      create or refresh testplan.csv
  sample    draw seeded samples and write workpaper skeletons
  validate  check workpapers (add --final for opinion, QA and description)
  qa        record an independent review of one workpaper
  rollup    summarize conclusions by criterion
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
from common.io import tool_version  # noqa: E402
from common import capture, connectors, ingest  # noqa: E402
from core import AuditError, Engagement, dump_yaml, load_json, read_csv, load_yaml  # noqa: E402


def cmd_init(a) -> int:
    root = Path(a.engagement)
    if (root / "engagement.yaml").exists():
        raise AuditError(f"{root}/engagement.yaml already exists.")
    cfg = {
        "schema_version": 1,
        "service_organization": a.org,
        "system": a.system,
        "service_auditor": "AI Audit",
        "auditor_location": "",
        "report_type": a.type,
        "language": a.language,
    }
    if a.type == 2:
        if not (a.start and a.end):
            raise AuditError("Type 2 needs --start and --end (the examination period).")
        cfg["period"] = {"start": a.start, "end": a.end}
    else:
        if not a.as_of:
            raise AuditError("Type 1 needs --as-of (the examination date).")
        cfg["as_of"] = a.as_of
    cfg["categories"] = a.categories.split(",")
    cfg["subservice_organizations"] = []
    entries = ingest.parse_options(a.connector, a.option)
    if len(entries) == 1:
        cfg["source"] = entries[0]
    else:
        cfg["sources"] = entries
    cfg["sampling_seed"] = secrets.randbelow(10**9)
    cfg["tool_version"] = tool_version()
    cfg["signoff"] = None
    dump_yaml(cfg, root / "engagement.yaml")
    Engagement(root).config  # validate
    print(f"Created {root}/engagement.yaml (sampling seed {cfg['sampling_seed']}). This will be an AI Audit, not an official SOC 2 audit. Add subservice organizations if any, then run ingest.")
    return 0


def cmd_ingest(a) -> int:
    eng = Engagement(a.engagement)
    src = {"connector": "+".join(x["connector"] for x in ingest.sources(eng.config))}
    manifest = ingest.run(eng, replace=a.replace)
    kinds = {}
    for art in manifest["artifacts"]:
        kinds[art["kind"]] = kinds.get(art["kind"], 0) + 1
    print(f"Ingested {len(manifest['artifacts'])} artifacts via {src['connector']}: " + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))
    if eng.workpaper_files():
        print("warning: workpapers already exist and may cite artifact IDs from the previous bundle; run validate.")
    return 0


def cmd_rollforward(a) -> int:
    from common.rollforward import rollforward

    prev = Engagement(a.previous)
    rtype = a.type or prev.report_type
    done = rollforward(prev.root, Path(a.engagement), description_file="system.yaml", findings_file="opinion.json",
                       as_of=a.as_of, start=a.start, end=a.end, point_in_time=rtype == 1)
    if a.type:
        cfg = load_yaml(Path(a.engagement) / "engagement.yaml")
        cfg["report_type"] = rtype
        dump_yaml(cfg, Path(a.engagement) / "engagement.yaml")
    Engagement(a.engagement).config  # validate
    for line in done:
        print(f"- {line}")
    print(f"Next: soc2.py ingest {a.engagement}, then plan. Review the previous exceptions in prior/ when testing the same controls.")
    return 0


def cmd_check(a) -> int:
    eng = Engagement(a.engagement)
    errors, warnings = checks.run(eng)
    return _report(errors, warnings, ok="Bundle intact. See review/coverage.md and review/requests.csv.")


def cmd_plan(a) -> int:
    eng = Engagement(a.engagement)
    todo = planning.plan(eng)
    if eng.config.get("tool_version") != tool_version():
        cfg = load_yaml(eng.config_path)
        cfg["tool_version"] = tool_version()
        dump_yaml(cfg, eng.config_path)
    print(f"Wrote {eng.testplan_path}.")
    if todo:
        print("Complete these rows (see references/planning.md), then run sample:")
        for t in todo:
            print(f"  - {t}")
        return 1
    print("All rows complete. Review them, then run sample.")
    return 0


def cmd_sample(a) -> int:
    eng = Engagement(a.engagement)
    log = planning.sample(eng, force=a.force)
    for line in log:
        print(f"  {line}")
    print(f"{len(log)} workpaper skeletons written to {eng.workpapers}." if log else "Workpapers already match the test plan.")
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
    print("This is an AI Audit, not an official SOC 2 audit.")
    print(f"Workpapers: {out['xlsx']}\nEvidence index: {out['evidence_index']}")
    return 0


def cmd_signoff(a) -> int:
    eng = Engagement(a.engagement)
    digest = review.signoff(eng, a.model)
    print(f"Signed by {a.model.strip()} (digest {digest[:16]}). Run render to produce the AI Audit PDF.")
    print("This is an AI Audit, not an official SOC 2 audit.")
    return 0


def cmd_status(a) -> int:
    root = Path(a.engagement)
    eng = Engagement(root)
    if (root / "engagement.yaml").exists():
        print(_version_note(eng), end="")
    if not eng.config_path.exists():
        return _next("No engagement yet.", f"soc2.py init {root} --org ... (see references/engagement-folder.md)")
    eng.config
    if not eng.manifest_path.exists():
        return _next("Engagement configured, no evidence yet.", f"soc2.py ingest {root}")
    if not (eng.review / "coverage.md").exists():
        return _next("Evidence ingested, not checked.", f"soc2.py check {root}")
    if not eng.testplan_path.exists():
        return _next("Bundle checked, no test plan.", f"soc2.py plan {root}")
    rows = read_csv(eng.testplan_path)
    incomplete = [r["control_id"] for r in rows if not r["frequency"] or not r["nature"]]
    if incomplete:
        return _next(f"Test plan has {len(incomplete)} incomplete rows: {', '.join(incomplete[:10])}",
                     "fill frequency and nature in testplan.csv (references/planning.md), then soc2.py sample")
    wps = eng.load_workpapers()
    if len(wps) < len(rows):
        return _next(f"{len(rows) - len(wps)} controls have no workpaper.", f"soc2.py sample {root}")
    pending = sorted(cid for cid, wp in wps.items() if wp.get("conclusion") == "pending")
    if pending:
        return _next(f"{len(wps) - len(pending)} of {len(wps)} controls tested. Pending: {', '.join(pending[:15])}{' ...' if len(pending) > 15 else ''}",
                     "test each pending control (references/control-testing.md), then soc2.py validate")
    errors, _ = review.validate(eng)
    if errors:
        return _next(f"All controls tested; {len(errors)} validation errors.", f"soc2.py validate {root}, fix, repeat")
    qa = load_json(eng.qa_path) if eng.qa_path.exists() else {"reviews": []}
    reviewed = {r["control_id"] for r in qa["reviews"]}
    if len(reviewed & set(wps)) < len(wps):
        return _next(f"QA reviewed {len(reviewed & set(wps))} of {len(wps)} workpapers.", "QA review (references/qa-review.md)")
    if not eng.opinion_path.exists():
        return _next("Testing and QA done, no opinion yet.", f"soc2.py rollup {root}, then write opinion.json (references/evaluating.md)")
    errors, _ = review.validate(eng, final=True)
    if errors:
        return _next(f"{len(errors)} final validation errors.", f"soc2.py validate {root} --final, fix, repeat")
    pdfs = sorted(eng.report.glob("*.pdf")) if eng.report.exists() else []
    if review.signed_off(eng):
        final_pdfs = [p for p in pdfs if not p.stem.endswith("-DRAFT")]
        if final_pdfs:
            return _next(f"Complete. AI Audit report: {final_pdfs[-1]}", "none")
        return _next("Signed; AI Audit PDF not rendered.", f"soc2.py render {root}")
    if not pdfs or not (eng.review / "packet.md").exists():
        return _next("Ready to sign.", f"soc2.py signoff {root} --model \"<model>\" && soc2.py render {root} && soc2.py packet {root}")
    return _next("Draft AI Audit ready.", f"soc2.py signoff {root} --model \"<model that ran this audit>\" && soc2.py render {root}")


def _next(state: str, step: str) -> int:
    print(f"State: {state}\nNext:  {step}")
    return 0

def _version_note(eng) -> str:
    """Tell the user when the skill changed since this engagement was planned, and that the work so far is kept."""
    from common.io import tool_version

    was, now = eng.config.get("tool_version"), tool_version()
    if was == now:
        return ""
    return (f"Note:  the skill is version {now}; this engagement was planned with {was or 'an earlier version'}. "
            "Run `plan` to pick up new or changed requirements (existing workpapers and auditor edits are kept), "
            "and `ingest --replace` for new connector features (unchanged evidence keeps its ID).\n")



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
    p = argparse.ArgumentParser(prog="soc2.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create engagement.yaml")
    s.add_argument("engagement")
    s.add_argument("--org", required=True, help="service organization legal name")
    s.add_argument("--system", required=True, help="name of the system under examination")
    s.add_argument("--type", type=int, choices=[1, 2], required=True)
    s.add_argument("--start")
    s.add_argument("--end")
    s.add_argument("--as-of")
    s.add_argument("--categories", default="security", help="comma-separated: security,availability,confidentiality,processing-integrity,privacy")
    s.add_argument("--language", default="en", choices=["en", "de"], help="language of the report (default en)")
    s.add_argument("--connector", required=True, action="append", choices=connectors.available(),
                   help="evidence source; repeat for several (e.g. --connector records --connector intake)")
    s.add_argument("--option", action="append", help="connector option key=value, or <connector>.key=value with several connectors (repeatable)")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("rollforward", help="start a new engagement from a finished one (settings and decisions carried over)")
    s.add_argument("previous", help="the finished engagement")
    s.add_argument("engagement", help="the new engagement folder")
    s.add_argument("--type", type=int, choices=[1, 2], help="report type, if different from the previous engagement")
    s.add_argument("--as-of")
    s.add_argument("--start")
    s.add_argument("--end")
    s.set_defaults(fn=cmd_rollforward)

    s = sub.add_parser("ingest", help="pull evidence into bundle/")
    s.add_argument("engagement")
    s.add_argument("--replace", action="store_true", help="pull again, keeping the old bundle aside")
    s.set_defaults(fn=cmd_ingest)

    for name, fn, help_ in [("check", cmd_check, "bundle integrity and coverage"), ("plan", cmd_plan, "create testplan.csv"),
                            ("rollup", cmd_rollup, "criterion summary"), ("packet", cmd_packet, "review packet"),
                            ("render", cmd_render, "build the report"), ("status", cmd_status, "progress and next step")]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("engagement")
        s.set_defaults(fn=fn)

    s = sub.add_parser("sample", help="draw samples, write workpaper skeletons")
    s.add_argument("engagement")
    s.add_argument("--force", action="store_true", help="overwrite workpapers whose plan changed")
    s.set_defaults(fn=cmd_sample)

    s = sub.add_parser("validate", help="check workpapers")
    s.add_argument("engagement")
    s.add_argument("--final", action="store_true", help="also check opinion, QA and system description")
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

    capture.add_parser(sub)

    argv, tail = capture.split_command(list(sys.argv[1:] if argv is None else argv))
    a = p.parse_args(argv)
    if tail:
        a.command = tail
    try:
        return a.fn(a)
    except AuditError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
