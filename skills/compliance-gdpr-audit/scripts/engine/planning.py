# Copied from shared/engines/requirements/planning.py by tools/sync.py. Edit that file, not this copy.
"""`plan` and `sample`: the test plan and reproducible sample selection.

testplan.csv is the auditor's document: which units this audit covers, how often
each operates, whether it is manual or automated, and which population it draws
from. `sample` turns it into workpaper skeletons with a seeded, repeatable sample
for every included unit.
"""

from __future__ import annotations

from collections import Counter

from common import sampling
from common.sampling import FREQUENCIES, NATURES
from core import CLI, PROFILE, REQ_PREFIX, AuditError, Engagement, dump_json, load_json, load_requirements, read_csv, write_csv

COLUMNS = ["control_id", "include", "frequency", "nature", "population", "sample_size", "notes"]


def plan(eng: Engagement) -> list[str]:
    """Create or refresh testplan.csv. Keeps auditor edits; returns rows that still need input."""
    existing = {r["control_id"]: r for r in read_csv(eng.testplan_path)} if eng.testplan_path.exists() else {}
    rows = []
    for c in eng.controls:
        row = existing.get(c["id"]) or {
            "control_id": c["id"],
            "include": "yes",
            "frequency": c.get("frequency", "").lower(),
            "nature": c.get("nature", "").lower(),
            "population": c.get("population", ""),
            "sample_size": "",
            "notes": "requirement audited directly; frequency and nature are catalog defaults, confirm them" if c["id"].startswith(REQ_PREFIX) else "",
        }
        row.setdefault("include", "yes")
        rows.append(row)
    removed = sorted(set(existing) - {c["id"] for c in eng.controls})
    write_csv(eng.testplan_path, rows, COLUMNS)
    todo = [f"{r['control_id']}: set {', '.join(p for p in ('frequency', 'nature') if not r[p])}" for r in rows if not r["frequency"] or not r["nature"]]
    todo += [f"{r['control_id']}: event-driven; set population to a PO-... artifact, or another frequency" for r in rows
             if r["frequency"] == "event" and not r["population"] and r.get("include", "yes") != "no"]
    todo += [f"{cid}: no longer a unit of this audit; row dropped" for cid in removed]
    return todo


def sample(eng: Engagement, force: bool = False) -> list[str]:
    """Validate testplan.csv and write workpaper skeletons. Returns a log of what was written."""
    rows, notes = _validated_plan(eng)
    controls = {c["id"]: c for c in eng.controls}
    log = [f"warning: {n}" for n in notes]
    for path in eng.workpaper_files():
        cid = load_json(path).get("control_id", path.stem)
        if cid in controls:
            continue
        if load_json(path).get("conclusion") not in (None, "pending") and not force:
            raise AuditError(f"{cid}: no longer in the control matrix but its workpaper has results. "
                             "Re-run with --force to discard them.")
        path.unlink()
        log.append(f"{cid}: no longer in the control matrix; workpaper removed")
    for row in rows:
        c = controls[row["control_id"]]
        path = eng.workpaper_path(c["id"])
        if row["include"] == "no":
            if path.exists():
                wp = load_json(path)
                if wp.get("conclusion") not in (None, "pending") and not force:
                    raise AuditError(f"{c['id']}: excluded in testplan.csv but its workpaper already has results. "
                                     "Re-run with --force to discard them, or include the control again.")
                path.unlink()
                log.append(f"{c['id']}: excluded from this audit; workpaper removed")
            continue
        planned = expected_plan(eng, row)
        if path.exists():
            wp = load_json(path)
            same_control = wp.get("control") == c["description"] and wp.get("criteria") == c["criteria"]
            if wp.get("plan") == planned and same_control:
                continue
            what = "the test plan" if same_control else "the control's description or criteria"
            if wp.get("conclusion") not in (None, "pending") and not force:
                raise AuditError(f"{c['id']}: {what} changed but the workpaper already has results. "
                                 "Re-run with --force to discard them and test again, or restore the previous version.")
        dump_json(skeleton(c, planned), path)
        log.append(f"{c['id']}: {planned['sample_size']} of {planned['population']['size'] if planned['population'] else 1} ({row['frequency']}, {row['nature']})")
    return log


def expected_plan(eng: Engagement, row: dict) -> dict:
    """The plan block `sample` writes for a testplan row. Deterministic for a given seed (common/sampling.py)."""
    start, end = eng.period
    population = None
    if row["population"]:
        population = (row["population"], [r["id"] for r in eng.population(row["population"])
                                          if sampling.in_period(r.get("date"), start, end, eng.point_in_time)])
    planned = sampling.plan(seed=f"{eng.config['sampling_seed']}:{row['control_id']}", freq=row["frequency"], nature=row["nature"],
                         start=start, end=end, point_in_time=eng.point_in_time, population=population, sample_size=row["sample_size"])
    if planned["population"] and planned["population"]["source"] in eng.artifacts:
        planned["population"]["sha256"] = eng.artifacts[planned["population"]["source"]]["sha256"]
    # Results hold for this audit type and these dates only: moving the as-of date or the period means testing again.
    planned["window"] = {"audit_type": eng.audit_type, "start": start.isoformat(), "end": end.isoformat()}
    return planned

def skeleton(control: dict, planned: dict) -> dict:
    return {
        "schema_version": 1,
        "control_id": control["id"],
        "control": control["description"],
        "criteria": control["criteria"],
        "plan": planned,
        "design": {"effective": None, "rationale": "", "evidence": []},
        "procedures": [],
        "attributes": {},
        "items": [{"id": item, "results": {}, "evidence": [], "note": ""} for item in planned["sample"]],
        "deviations": [],
        "population_check": None,
        "conclusion": "pending",
        "scope_limitation": None,
        "observations": [],
        "confidence": None,
        "prepared_by": None,
    }


def surveillance_gaps(eng: Engagement, included: set[str]) -> list[str]:
    """Requirements every partial audit (ISO surveillance) covers that no included unit addresses.

    The catalog marks them with the flag named in profile `partial.must_cover` (ISO: `surveillance`)."""
    covered = {x for c in eng.controls if c["id"] in included for x in c["criteria"]}
    return [r["id"] for r in load_requirements() if r.get((PROFILE.get("partial") or {}).get("must_cover", "surveillance")) and r["id"] not in covered]


def _validated_plan(eng: Engagement) -> tuple[list[dict], list[str]]:
    if not eng.testplan_path.exists():
        raise AuditError(f"No testplan.csv. Run `{CLI} plan` first.")
    rows = read_csv(eng.testplan_path)
    control_ids = {c["id"] for c in eng.controls}
    errors, notes = [], []
    for i, r in enumerate(rows, start=2):
        where = f"testplan.csv line {i} ({r.get('control_id')})"
        r["include"] = (r.get("include") or "yes").lower()
        if r.get("control_id") not in control_ids:
            errors.append(f"{where}: unknown control")
        if r["include"] not in ("yes", "no"):
            errors.append(f"{where}: include must be yes or no")
        if r["include"] == "no":
            if not eng.partial:
                errors.append(f"{where}: only a partial audit (such as an ISO surveillance audit) may leave a unit out; a {eng.audit_type} audit covers every requirement in scope")
            elif not r.get("notes"):
                errors.append(f"{where}: explain in notes why this unit is left out of the {eng.audit_type} audit")
            continue
        if r.get("frequency") not in FREQUENCIES:
            errors.append(f"{where}: frequency must be one of {', '.join(FREQUENCIES)}")
        if r.get("nature") not in NATURES:
            errors.append(f"{where}: nature must be one of {', '.join(NATURES)}")
        if r.get("frequency") == "event" and not r.get("population"):
            errors.append(f"{where}: event-driven controls need a population artifact ID (PO-...)")
        if r.get("population") and r["population"] not in eng.artifacts:
            errors.append(f"{where}: population {r['population']} is not in the bundle")
        elif r.get("population"):
            pop_rows = eng.population(r["population"])
            ids = [x["id"] for x in pop_rows]
            dupes = sorted(i for i, n in Counter(ids).items() if n > 1)
            if dupes:
                errors.append(f"{where}: population {r['population']} repeats item IDs {dupes[:5]}; each event must appear once")
            bad = [x["id"] for x in pop_rows if sampling.parse_date(x.get("date")) is None]
            if bad:
                errors.append(f"{where}: population {r['population']} has items without a valid date {bad[:5]}; correct them "
                              "(YYYY-MM-DD) so no event drops out of the sample unseen")
        if r.get("sample_size"):
            if not r["sample_size"].isdigit():
                errors.append(f"{where}: sample_size must be a whole number or empty")
            elif not r.get("notes"):
                errors.append(f"{where}: explain a sample_size override in notes")
    missing = control_ids - {r.get("control_id") for r in rows}
    if missing:
        errors.append(f"testplan.csv is missing units {sorted(missing)}; run `{CLI} plan` again")
    if eng.partial:
        included = {r["control_id"] for r in rows if r["include"] == "yes"}
        gaps = surveillance_gaps(eng, included)
        if gaps:
            errors.append(f"a {eng.audit_type} audit must cover {', '.join(gaps)}; include a unit mapped to each")
        hint = (PROFILE.get("partial") or {}).get("rotate_prefix")
        if hint and not any(x.startswith(hint) for c in eng.controls if c["id"] in included for x in c["criteria"]):
            notes.append(f"no {hint} requirement is included in this {eng.audit_type} audit; sample some so all of them are covered over the certification cycle")
    if errors:
        raise AuditError("testplan.csv needs fixes:\n  " + "\n  ".join(errors))
    return rows, notes
