# Copied from shared/lib/rollforward.py by tools/sync.py. Edit that file, not this copy.
"""`rollforward`: start the next engagement from a finished one, instead of from scratch.

Kept as the starting point of the new engagement:
  engagement.yaml     every setting (organization, scope, roles, sources, repo, language,
                      included optional requirements), with the new date or period, a new
                      sampling seed, no sign-off, and `prior:` pointing back
  the description     system.yaml / isms.yaml / context.yaml at the root (re-confirm it)
  testplan.csv        the auditor's frequency, nature, population and override decisions

Kept for reference under prior/ (never cited as current evidence):
  prior/findings.json (or opinion.json), prior/workpapers/, prior/report-data.json,
  prior/intake/       the earlier captures: exports and answers can be re-captured after
                      the user confirms they are still current; configuration is captured again

The new engagement must follow up every previous finding (`prior_followup` in
findings.json: closed, open or partly). The evidence plan lists the earlier exports and
answers, so the user is asked only about what changed.
"""

from __future__ import annotations

import secrets
import shutil
from pathlib import Path

from .io import AuditError, dump_yaml, load_yaml, tool_version

CONFIG_DROP = ("signoff", "period", "as_of")


def rollforward(prev: Path, new: Path, *, description_file: str, findings_file: str, as_of: str | None = None,
                start: str | None = None, end: str | None = None, point_in_time: bool) -> list[str]:
    """Create `new` from `prev`. Returns what was carried over, for the user."""
    prev, new = Path(prev).resolve(), Path(new)
    if not (prev / "engagement.yaml").exists():
        raise AuditError(f"{prev} has no engagement.yaml")
    if (new / "engagement.yaml").exists():
        raise AuditError(f"{new}/engagement.yaml already exists")
    if point_in_time and not as_of:
        raise AuditError("this audit type is as of a date: give --as-of")
    if not point_in_time and not (start and end):
        raise AuditError("this audit type samples a period: give --start and --end")
    cfg = load_yaml(prev / "engagement.yaml")
    for key in CONFIG_DROP:
        cfg.pop(key, None)
    if point_in_time:
        cfg["as_of"] = as_of
    else:
        cfg["period"] = {"start": start, "end": end}
    cfg.update(sampling_seed=secrets.randbelow(10**9), signoff=None, prior=str(prev), tool_version=tool_version())
    new.mkdir(parents=True, exist_ok=True)
    dump_yaml(cfg, new / "engagement.yaml")
    done = ["engagement.yaml: settings kept, new date, new sampling seed, not signed"]
    if (prev / description_file).exists():
        shutil.copyfile(prev / description_file, new / description_file)
        done.append(f"{description_file}: carried over; confirm it is still accurate")
    if (prev / "testplan.csv").exists():
        shutil.copyfile(prev / "testplan.csv", new / "testplan.csv")
        done.append("testplan.csv: earlier decisions kept; run plan to add new requirements")
    prior = new / "prior"
    prior.mkdir(exist_ok=True)
    for name in (findings_file, "report/report-data.json"):
        if (prev / name).exists():
            shutil.copyfile(prev / name, prior / Path(name).name)
    for folder in ("workpapers", "intake"):
        if (prev / folder).is_dir():
            shutil.copytree(prev / folder, prior / folder)
    done.append("prior/: previous findings, workpapers, report data and captures, for reference")
    return done


def prior_findings(eng, findings_file: str) -> list[dict]:
    """Findings of the engagement this one was rolled forward from."""
    path = eng.root / "prior" / findings_file
    if not eng.config.get("prior") or not path.exists():
        return []
    import json

    return json.loads(path.read_text(encoding="utf-8")).get("findings") or []


def prior_captures(root: Path) -> list[dict]:
    """Earlier exports and answers, by recipe item, so the plan can ask whether they are still current."""
    from .capture import entries

    out = []
    for path, meta in entries(Path(root) / "prior"):
        if meta.get("via") in ("export", "answer"):
            out.append({"file": f"prior/intake/{path.name}", "via": meta["via"], "title": meta["title"], "recipe": meta.get("recipe") or "",
                        "requirements": meta.get("requirements") or [], "at": (meta.get("at") or "")[:10], "question": meta.get("question") or ""})
    return out
