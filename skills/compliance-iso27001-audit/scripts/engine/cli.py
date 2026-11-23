# Copied from shared/engines/requirements/cli.py by tools/sync.py. Edit that file, not this copy.
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
from common.io import tool_version  # noqa: E402
from common import capture, connectors, detect, ingest  # noqa: E402
from core import APPLICABILITY, ASSETS, AUDIT_TYPES, CLI, PROFILE, AuditError, Engagement, dump_yaml, load_json, load_requirements, load_yaml  # noqa: E402

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
    print(f"Created {root}/engagement.yaml (sampling seed {cfg['sampling_seed']}). {NOT_CERT} Run ingest next.")
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
    atype = a.type or prev.audit_type
    if atype not in AUDIT_TYPES:
        raise AuditError(f"--type must be one of {', '.join(AUDIT_TYPES)}")
    done = rollforward(prev.root, Path(a.engagement), description_file=prev.framework.description["file"], findings_file="findings.json",
                       as_of=a.as_of, start=a.start, end=a.end, point_in_time=bool(PROFILE["audit_types"][atype].get("as_of")))
    if a.type:
        cfg = load_yaml(Path(a.engagement) / "engagement.yaml")
        cfg["audit_type"] = atype
        dump_yaml(cfg, Path(a.engagement) / "engagement.yaml")
    Engagement(a.engagement).config  # validate
    for line in done:
        print(f"- {line}")
    print(f"Next: {CLI} ingest {a.engagement} (and detect, for an app), then plan. Every previous finding needs a follow-up in findings.json.")
    return 0


def cmd_probe(a) -> int:
    """Run an active read-only check against the live system and record it as evidence."""
    import json

    from common import codescan, probes

    if not a.authorized:
        raise AuditError("probe sends requests to the live system. Confirm with the user that they may test it, then add --authorized.")
    eng = Engagement(a.engagement)
    repo = Path(a.repo or eng.config.get("repo") or ".")
    stack = load_yaml(eng.review / "stack.yaml") if (eng.review / "stack.yaml").exists() else {}
    if a.name == "supabase-anon":
        url, key = codescan.supabase_anon_key(repo)
        url = a.url or url
        if not (url and key):
            raise AuditError("no Supabase URL and anon key found in the app's client code; give --url, or run detect --repo first")
        tables = sorted(set(stack.get("tables") or []) | set(filter(None, (a.tables or "").split(","))))
        buckets = sorted(set(stack.get("buckets") or []) | set(filter(None, (a.buckets or "").split(","))))
        result = probes.supabase_anon(url, key, tables, buckets)
        reqs = ["SEC-AC-01", "SEC-AC-02", "SEC-AC-06"]
        title = "Anonymous access to the live Supabase API (row counts and bucket listing, no data read)"
    else:
        raise AuditError(f"unknown probe {a.name}; available: {', '.join(probes.PROBES)}")
    known = {r["id"] for r in eng.requirements}
    path = capture.capture(eng.root, via="probe", title=title, payload=json.dumps(result, indent=2).encode(),
                           requirements=[r for r in reqs if r in known], recipe=a.name, by="probe")
    s = result["summary"]
    print(f"Probed {len(result['tables'])} tables and {len(result['buckets'])} buckets. Readable by anyone: "
          f"{', '.join(s['tables_readable_by_anyone']) or 'none'}; listable buckets: {', '.join(s['buckets_listable_by_anyone']) or 'none'}.")
    print(f"Recorded as {path.name}. Run ingest --replace.")
    return 0


def cmd_detect(a) -> int:
    """Scan the repository, match stack recipes, record the scan as evidence and write the evidence plan."""
    import json

    eng = Engagement(a.engagement)
    repo = Path(a.repo or eng.config.get("repo") or ".").expanduser().resolve()
    if not repo.is_dir():
        raise AuditError(f"--repo {repo} is not a directory; give the path of the application's repository checkout")
    recipes = detect.load_recipes(ASSETS / "recipes")
    components, scan = detect.detect(repo, recipes)
    # Remember the repository, and switch on the optional requirements the stack uses (AI processing, file storage).
    cfg = load_yaml(eng.config_path)
    cfg["repo"] = str(repo)
    enabled = [x for c in components for x in c.get("enables") or []]
    if enabled:
        cfg["include_optional"] = sorted(set(cfg.get("include_optional") or []) | set(enabled))
    dump_yaml(cfg, eng.config_path)
    eng = Engagement(a.engagement)
    scan_reqs = sorted({r for c in components for i in c.get("items") or [] if i.get("scan_rules") for r in i.get("requirements") or []})
    capture.capture(eng.root, via="scan", title=f"Code scan of the {repo.name} repository", payload=json.dumps(scan, indent=2).encode(),
                    requirements=[r for r in scan_reqs if r in {x["id"] for x in eng.requirements}], by="codescan (detect)")
    catalog = {r["id"]: r for r in load_requirements(eng.language)}
    in_scope = {r["id"] for r in eng.requirements}
    rows = detect.evidence_plan(components, scan, catalog, in_scope, eng.language)
    covered = {x for r in rows for x in r["requirements"]}
    uncovered = [catalog[i] for i in sorted(in_scope - covered)]
    from common.rollforward import prior_captures

    detect.write_plan(eng.review, components, scan, rows, uncovered, prior=prior_captures(eng.root))
    names = ", ".join(c.get("title", c["component"]) for c in components) or "nothing recognized"
    print(f"Detected: {names}. {len(scan['findings'])} code scan findings, {len(scan['services'])} third-party services.")
    print(f"Evidence plan: {eng.review / 'evidence-plan.md'} ({len(rows)} items, {len(uncovered)} requirements without a recipe).")
    if enabled:
        print(f"Included optional requirements the stack uses: {', '.join(sorted(set(enabled)))}")
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


def cmd_draft(a) -> int:
    import draft

    counts = draft.draft(Engagement(a.engagement))
    print(f"Drafted {counts['drafted']} units; {counts['no_evidence']} had no linked evidence and are not-audited "
          f"(re-run draft after new evidence); {counts['kept']} already worked on were left alone.")
    print(draft.batches(Engagement(a.engagement)), end="")
    return 0


def cmd_unit(a) -> int:
    import draft

    eng = Engagement(a.engagement)
    print(draft.unit_pack(eng, a.unit) if a.unit else draft.batches(eng), end="")
    return 0


def cmd_validate(a) -> int:
    eng = Engagement(a.engagement)
    if a.unit:
        wp_path = eng.workpaper_path(a.unit)
        if not wp_path.exists():
            raise AuditError(f"no workpaper for {a.unit}")
        plan_rows = {r["control_id"]: r for r in eng.testplan()}
        errors, warnings = review._check_workpaper(eng, a.unit, load_json(wp_path), plan_rows.get(a.unit))
        return _report(errors, warnings, ok=f"{a.unit} valid.")
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
    if (root / "engagement.yaml").exists():
        print(_version_note(eng), end="")
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
    s.add_argument("--connector", required=True, action="append", choices=connectors.available(),
                   help="evidence source; repeat for several (e.g. --connector records --connector intake)")
    s.add_argument("--option", action="append", help="connector option key=value, or <connector>.key=value with several connectors (repeatable)")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("rollforward", help="start a new engagement from a finished one (settings, decisions and findings carried over)")
    s.add_argument("previous", help="the finished engagement")
    s.add_argument("engagement", help="the new engagement folder")
    s.add_argument("--type", help="audit type, if different from the previous engagement")
    s.add_argument("--as-of")
    s.add_argument("--start")
    s.add_argument("--end")
    s.set_defaults(fn=cmd_rollforward)

    s = sub.add_parser("probe", help="active read-only check of the live system (supabase-anon: what anonymous visitors can read)")
    s.add_argument("engagement")
    s.add_argument("name", help="supabase-anon")
    s.add_argument("--authorized", action="store_true", help="the user confirmed they may test this system")
    s.add_argument("--repo", help="repository checkout (default: the engagement's repo)")
    s.add_argument("--url", help="API base URL, if not the one in the app's code")
    s.add_argument("--tables", help="extra table names, comma-separated")
    s.add_argument("--buckets", help="extra bucket names, comma-separated")
    s.set_defaults(fn=cmd_probe)

    s = sub.add_parser("detect", help="scan the app repository, match stack recipes, write the evidence plan")
    s.add_argument("engagement")
    s.add_argument("--repo", help="path of the application's repository checkout (remembered in engagement.yaml)")
    s.set_defaults(fn=cmd_detect)

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

    s = sub.add_parser("draft", help="pre-fill pending workpapers from the bundle (evidence links, attributes, no-evidence units)")
    s.add_argument("engagement")
    s.set_defaults(fn=cmd_draft)

    s = sub.add_parser("unit", help="one unit's context pack for a worker; without an ID, the pending units in batches")
    s.add_argument("engagement")
    s.add_argument("unit", nargs="?")
    s.set_defaults(fn=cmd_unit)

    s = sub.add_parser("validate", help="check workpapers")
    s.add_argument("engagement")
    s.add_argument("--final", action="store_true", help="also check findings, QA and the description")
    s.add_argument("--unit", help="check only this unit's workpaper (fast, for a worker)")
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

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except AuditError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
