# Copied from shared/lib/connectors/records.py by tools/sync.py. Edit that file, not this copy.
"""Records connector: build the bundle from a compliance-prep records folder (YAML in git).

This is how an audit reads what the compliance-prep skill keeps when a company has no
compliance platform. The folder layout is the prep skill's (its
scripts/connectors/folder.py and assets/folder-template/):

  frameworks/<name>.yaml   framework controls (ref, name, measures, documents, applicable, justification)
  measures.yaml            the organization's controls       -> controls.csv
  evidence/<measure id>/   evidence files                    -> evidence, linked to that control
  documents.yaml           policies with version, approval, signatures -> policy artifacts
  documents/<id>.<ext>     optional document text            -> attached to the policy artifact
  people.yaml              contract_start / contract_end      -> hires and terminations populations
  vendors.yaml             third parties (added_at)           -> vendors population and register export
  findings.yaml            nonconformities                    -> nonconformities population and register export
  risks.yaml, assets.yaml, data.yaml, audits.yaml, access-reviews.yaml, tasks.yaml -> register exports
  system.yaml              {approved, sections: {product, architecture, team, processes, customers}}
                                                             -> draft description for the audited framework
  (git history)            commits touching the folder        -> change history export; file dates

Which framework file is audited: `source.options.framework` (its id or file name), or
the one whose name matches the audited framework, preferring the separate
"<Framework> Criteria, AI Audited" copy the prep skill sets up for an AI Audit.

Everything in the folder is provided by the organization (`obtained: client`), not
pulled from a system of record. Git dates are the commit dates of each file.

Options (engagement.yaml source.options):
  path        records folder, relative to the engagement folder or absolute (default: records)
  framework   optional framework id or file stem in frameworks/
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ..bundle import BundleWriter, slug
from ..capture import git_read
from ..io import AuditError, parse_date

REGISTERS = (  # file, title, hint topic
    ("risks.yaml", "Risk register (records)", "risks"),
    ("assets.yaml", "Asset inventory (records)", "assets"),
    ("data.yaml", "Data inventory and classification (records)", "data"),
    ("audits.yaml", "Audits recorded (records)", "audits"),
    ("access-reviews.yaml", "Access reviews with entries (records)", "access_entries"),
    ("tasks.yaml", "Compliance tasks (records)", "obligations"),
)


def pull(writer: BundleWriter, options: dict, engagement) -> None:
    root = Path(options.get("path", "records"))
    if not root.is_absolute():
        root = engagement.root / root
    if not root.is_dir():
        raise AuditError(f"Records connector: {root} does not exist. Set source.options.path in engagement.yaml "
                         "to the compliance-prep records folder.")
    writer.source = str(root)
    fw = writer.framework
    hint = fw.hint
    start, end = engagement.period
    # Point in time (SOC 2 Type 1, ISO Stage 1, assessments): every event up to the as-of date counts.
    as_of = getattr(engagement, "point_in_time", None)
    as_of = bool(as_of) if as_of is not None else getattr(engagement, "report_type", None) == 1
    in_scope = (lambda d: d <= end) if as_of else (lambda d: start <= d <= end)
    git = _Git(root)

    def read(name: str, default=None):
        p = root / name
        data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None
        return data if data is not None else ([] if default is None else default)

    def export(items, name: str, title: str, requirements=(), source_ref: str = "") -> None:
        writer.add_bytes(json.dumps(items, indent=2, default=str), f"{slug(name)}.json", title=title, requirements=requirements,
                         obtained="client", source_ref=source_ref, date=git.last(source_ref))

    # 1. The framework file: its controls name requirement IDs and link measures and documents.
    framework = _pick_framework(root, fw, options.get("framework"))
    fw_controls = framework.get("controls") or []
    known = {str(e["id"]) for e in fw.entries()}
    req_ids: dict[str, list[str]] = {}
    for c in fw_controls:
        ref = str(c.get("ref") or "")
        ids = [ref] if ref in known else fw.find(ref, annex=ref.upper().startswith("A") if fw.name == "iso27001" else None)
        if not ids:
            ids = fw.find(c.get("name"))
        if not ids:
            writer.warn(f"framework control '{ref} {c.get('name') or ''}' has no recognizable {fw.name} requirement ID")
        req_ids[ref] = ids

    # 2. Measures are the organization's controls; requirements come from the framework controls linking them.
    measures = read("measures.yaml")
    measure_reqs: dict[str, list[str]] = {}
    for c in fw_controls:
        for mid in c.get("measures") or []:
            reqs = measure_reqs.setdefault(str(mid), [])
            reqs += [x for x in req_ids.get(str(c.get("ref") or ""), []) if x not in reqs]
    rows = []
    for m in measures:
        mid = str(m["id"])
        if mid in known or mid.startswith("REQ-"):
            raise AuditError(f"measures.yaml: measure id '{mid}' collides with a requirement ID; rename it.")
        rows.append({
            "id": mid, "title": m.get("name") or mid,
            "description": " ".join(x for x in (m.get("description") or "", f"(state: {m.get('state', 'UNKNOWN')})") if x),
            "criteria": measure_reqs.get(mid, []), "owner": m.get("owner") or "", "source_ref": f"measures.yaml#{mid}",
        })
    unmapped = [r["id"] for r in rows if not r["criteria"]]
    if unmapped:
        writer.warn(f"measures not linked to any {fw.name} requirement in {framework['_file']}: {', '.join(unmapped)}")

    # 3. Statement of Applicability, from the framework file's applicable / justification (ISO 27001).
    if fw.soa:
        states = {str(m["id"]): m.get("state") for m in measures}
        soa_rows = []
        for c in fw_controls:
            ids = [x for x in req_ids.get(str(c.get("ref") or ""), []) if x.startswith("A.")]
            if not ids or "applicable" not in c:
                continue
            linked = [states.get(str(mid)) for mid in c.get("measures") or []]
            status = ("implemented" if linked and all(s == "IMPLEMENTED" for s in linked)
                      else "partial" if any(s == "IMPLEMENTED" for s in linked) else "not-implemented" if linked else "")
            soa_rows.append({"control": ids[0], "applicable": bool(c["applicable"]), "justification": c.get("justification") or "",
                             "status": status, "reference": framework.get("name") or ""})
        if soa_rows:
            writer.set_soa(soa_rows, obtained="client", source_ref=framework["_file"])
        else:
            writer.warn(f"{framework['_file']} records no applicability for Annex A controls; request the Statement of Applicability (clause 6.1.3 d)")

    # 4. Populations.
    people = read("people.yaml")
    hires, terms = [], []
    for p in people:
        s, e = parse_date(p.get("contract_start")), parse_date(p.get("contract_end"))
        base_row = {"name": p.get("name") or "", "email": p.get("email") or "", "state": p.get("state") or ""}
        if s and in_scope(s):
            hires.append({"id": f"H-{slug(str(p['id']))}", "date": s.isoformat(), **base_row})
        if e and in_scope(e):
            terms.append({"id": f"T-{slug(str(p['id']))}", "date": e.isoformat(), **base_row})
    if people and not any(p.get("contract_start") for p in people):
        writer.warn("people.yaml has no contract_start dates; the hires population is empty")
    pop_hires = writer.add_population("hires", hires, title="New hires in period (records, contract_start)", obtained="client", source_ref="people.yaml")
    pop_terms = writer.add_population("terminations", terms, title="Terminations in period (records, contract_end)", obtained="client", source_ref="people.yaml")
    export(people, "people", "People register (records)", source_ref="people.yaml")

    vendors = read("vendors.yaml")
    if vendors:
        export(vendors, "vendors-register", "Third parties with DPA status (records)", hint("vendors"), "vendors.yaml")
        first = git.first("vendors.yaml")
        writer.add_population("vendors", [
            {"id": f"V-{slug(str(v['id']))}", "date": str(v.get("added_at") or first or "")[:10], "name": v.get("name") or "",
             "category": v.get("category") or ""}
            for v in vendors if v.get("added_at") or first
        ], title="Third parties (records)", obtained="client", source_ref="vendors.yaml")

    findings = read("findings.yaml")
    pop_ncs = None
    if (root / "findings.yaml").exists():
        export(findings, "findings-register", "Findings register (records): nonconformities, observations and exceptions", hint("findings"), "findings.yaml")
        ncs = [{"id": str(f.get("ref") or f["id"]), "date": str(f.get("identified_on") or f.get("created_at") or "")[:10],
                "kind": f.get("kind"), "status": f.get("status"), "priority": f.get("priority") or ""}
               for f in findings if "NONCONFORMITY" in str(f.get("kind") or "").upper() and (f.get("identified_on") or f.get("created_at"))]
        pop_ncs = writer.add_population("nonconformities", ncs, title="Nonconformities identified (records)", obtained="client", source_ref="findings.yaml")

    for row in rows:
        text = (row["title"] + " " + row["description"]).lower()
        if any(k in text for k in ("terminat", "offboard", "deprovision")):
            row["population"] = pop_terms
        elif any(k in text for k in ("onboard", "new hire", "background check", "screening")):
            row["population"] = pop_hires
        elif pop_ncs and any(k in text for k in ("nonconformit", "corrective action")):
            row["population"] = pop_ncs
    writer.set_controls(rows)

    # 5. Evidence: evidence/<measure id>/<file>, dated by the commit that added it.
    ids = {r["id"] for r in rows}
    ev_root = root / "evidence"
    for path in sorted(p for p in ev_root.rglob("*") if p.is_file() and not p.name.startswith(".")) if ev_root.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        first_dir = path.relative_to(ev_root).parts[0]
        controls = [first_dir] if first_dir in ids else []
        if not controls:
            writer.warn(f"{rel}: evidence folder '{first_dir}' is not a measure id")
        writer.add_file(path, title=path.stem.replace("_", " ").replace("-", " "), controls=controls, requirements=measure_reqs.get(first_dir, []),
                        date=git.first(rel), obtained="client", source_ref=rel)

    # 6. Policies: metadata from documents.yaml, text from documents/<id>.* when present.
    doc_controls: dict[str, set] = {}
    doc_reqs: dict[str, list[str]] = {}
    for m in measures:
        for did in m.get("documents") or []:
            doc_controls.setdefault(str(did), set()).add(str(m["id"]))
    for c in fw_controls:
        for did in c.get("documents") or []:
            reqs = doc_reqs.setdefault(str(did), [])
            reqs += [x for x in req_ids.get(str(c.get("ref") or ""), []) if x not in reqs]
    for d in read("documents.yaml"):
        did = str(d["id"])
        title = d.get("title") or did
        body_file = next(iter(sorted((root / "documents").glob(f"{did}.*"))), None) if (root / "documents").is_dir() else None
        approval = (f"Approved by {d['approved_by']} on {str(d.get('approved_at') or 'n/a')[:10]}" if d.get("approved_by")
                    else "No approval recorded")
        signatures = f"Signed by {', '.join(d['signed_by'])}" if d.get("signed_by") else "No signatures recorded"
        body = (f"# {title}\n\nversion {d.get('version') or 'n/a'}, published {str(d.get('published_at') or 'n/a')[:10]}"
                f"{' (a newer draft exists)' if d.get('draft_newer') else ''}\n\n{approval}\n\n{signatures}\n\n"
                + (body_file.read_text(encoding="utf-8", errors="replace") if body_file and body_file.suffix in (".md", ".txt")
                   else f"Document text: {body_file.name if body_file else 'not in the records folder'}\n"))
        writer.add_bytes(body, f"{slug(title)}.md", title=f"Policy: {title}", kind="policy", controls=sorted(doc_controls.get(did, set()) & ids),
                         requirements=doc_reqs.get(did, []), date=str(d.get("published_at") or "")[:10] or None, obtained="client",
                         source_ref=f"documents.yaml#{did}")
        if body_file and body_file.suffix not in (".md", ".txt"):
            writer.add_file(body_file, title=f"Policy document: {title}", kind="policy", controls=sorted(doc_controls.get(did, set()) & ids),
                            requirements=doc_reqs.get(did, []), date=git.first(body_file.relative_to(root).as_posix()), obtained="client",
                            source_ref=body_file.relative_to(root).as_posix())

    # 7. Registers.
    for name, title, topic in REGISTERS:
        if (root / name).exists():
            export(read(name), Path(name).stem, title, hint(topic), name)

    # 8. Change history of the records: git is their change record.
    log = git.log()
    if log:
        export(log, "records-change-history", "Change history of the records folder (git log)", hint("obligations"), "git log")
    else:
        writer.warn("the records folder is not in a git repository; there is no change history to show who changed which record")

    # 9. Draft description from system.yaml. The organization must complete it for the report.
    system = read("system.yaml", {})
    sections = (system or {}).get("sections") or {}
    draft = fw.draft_description(sections)
    if (system or {}).get("approved"):
        draft["note"] = "system.yaml in the records folder is marked approved; this draft is still not the description printed in the report"
    writer.set_description(draft, obtained="client")


def _pick_framework(root: Path, fw, wanted: str | None) -> dict:
    files = sorted((root / "frameworks").glob("*.yaml")) if (root / "frameworks").is_dir() else []
    loaded = []
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data["_file"] = path.relative_to(root).as_posix()
        data.setdefault("id", path.stem)
        loaded.append(data)
    if wanted:
        for f in loaded:
            if wanted in (str(f["id"]), Path(f["_file"]).stem):
                return f
        raise AuditError(f"Records connector: no framework '{wanted}' in {root / 'frameworks'}.")
    matches = [f for f in loaded if fw.matches_platform(f.get("name") or f["id"])]
    if not matches:
        names = ", ".join(f.get("name") or f["id"] for f in loaded) or "none"
        raise AuditError(f"Records connector: no {fw.name} framework in {root / 'frameworks'} (found: {names}). "
                         "Set source.options.framework.")
    matches.sort(key=lambda f: "ai audited" not in (f.get("name") or "").lower())
    return matches[0]


class _Git:
    """Commit dates and history of the records folder, when it is a git checkout."""

    def __init__(self, root: Path):
        self.root = root
        self.ok = self._run("rev-parse", "--is-inside-work-tree") == "true"

    def _run(self, *args: str) -> str:
        return (git_read(self.root, *args) or "").strip()

    def first(self, rel: str | None) -> str | None:
        """Date the file was added (first commit), or None."""
        if not self.ok or not rel or not (self.root / rel).exists():
            return None
        dates = self._run("log", "--follow", "--format=%cs", "--", rel).splitlines()
        return dates[-1] if dates else None

    def last(self, rel: str | None) -> str | None:
        if not self.ok or not rel or not (self.root / rel).exists():
            return None
        return self._run("log", "-1", "--format=%cs", "--", rel) or None

    def log(self) -> list[dict]:
        if not self.ok:
            return []
        out = self._run("log", "--format=%H%x1f%cs%x1f%an%x1f%s", "--name-only", "--", ".")
        entries, cur = [], None
        for line in out.splitlines():
            if "\x1f" in line:
                sha, date, author, subject = line.split("\x1f", 3)
                cur = {"commit": sha[:12], "date": date, "author": author, "subject": subject, "files": []}
                entries.append(cur)
            elif line.strip() and cur is not None:
                cur["files"].append(line.strip())
        return entries
