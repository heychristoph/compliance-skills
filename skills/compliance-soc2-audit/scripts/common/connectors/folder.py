# Copied from shared/lib/connectors/folder.py by tools/sync.py. Edit that file, not this copy.
"""Folder connector: build the bundle from an export folder on disk.

This is the universal path. Any platform export, or files the organization
uploads, can be arranged into this layout (see references/connectors/folder.md):

    <path>/
      controls.csv            required: id,title,description,criteria[,owner,frequency,nature,population]
      soa.csv                 Statement of Applicability (ISO 27001): control,applicable,justification[,status,reference]
      system.yaml | isms.yaml | context.yaml   the description the audited framework uses (SOC 2 | ISO 27001 | GDPR, NIS2)
      populations/<name>.csv  first columns: id,date
      policies/<file>         policies, procedures and other documents
      evidence/<id>/<file>    evidence, grouped by the control ID or requirement ID (CC6.1, A.5.7, Art.30(1)) it supports
      evidence.csv            optional metadata: path,controls,requirements,title,date,obtained,kind
"""

from __future__ import annotations

from pathlib import Path

from ..bundle import BundleWriter, slug
from ..io import AuditError, load_yaml, read_csv


def pull(writer: BundleWriter, options: dict, engagement) -> None:
    root = Path(options.get("path", "export"))
    if not root.is_absolute():
        root = engagement.root / root
    if not root.is_dir():
        raise AuditError(f"Folder connector: {root} does not exist. Set source.options.path in engagement.yaml.")
    writer.source = str(root)
    obtained_default = options.get("obtained", "client")
    fw = writer.framework
    known = {str(e["id"]) for e in fw.entries()}

    controls_csv = root / "controls.csv"
    if not controls_csv.exists():
        raise AuditError(f"Folder connector: {controls_csv} is required (the control matrix).")
    rows = read_csv(controls_csv)
    missing = [c for c in ("id", "description", "criteria") if rows and c not in rows[0]]
    if missing:
        raise AuditError(f"controls.csv is missing columns: {', '.join(missing)}")
    control_ids = {r["id"] for r in rows}
    clash = sorted(control_ids & set(known)) + sorted(c for c in control_ids if c.startswith("REQ-"))
    if clash:
        raise AuditError(f"controls.csv: control IDs {clash} collide with requirement IDs; rename them (e.g. C-01).")

    # Populations first, so controls.csv can reference them by file name or artifact ID.
    population_ids = {}
    for path in sorted((root / "populations").glob("*.csv")):
        pop_rows = read_csv(path)
        population_ids[path.stem] = writer.add_population(
            path.stem, pop_rows, title=f"Population: {path.stem.replace('-', ' ')}", obtained=obtained_default, source_ref=path.name
        )
    for row in rows:
        ref = row.get("population", "")
        if ref and not ref.startswith("PO-"):
            row["population"] = population_ids.get(Path(ref).stem, f"PO-{slug(Path(ref).stem)}")
        ids = row.get("criteria", "").replace(",", " ").split()
        exact = [x for x in ids if x in known]
        parsed = writer.find(" ".join(x for x in ids if x not in known))
        row["criteria"] = list(dict.fromkeys(exact + parsed))
    writer.set_controls(rows)

    if fw.soa and (root / "soa.csv").exists():
        soa = read_csv(root / "soa.csv")
        if soa and "control" not in soa[0]:
            raise AuditError("soa.csv needs a 'control' column with Annex A IDs (A.5.1 ... A.8.34).")
        for r in soa:
            ids = writer.find(r["control"], annex=True)
            r["control"] = ids[0] if ids else r["control"]
        writer.set_soa(soa, obtained=obtained_default, source_ref="soa.csv")
    elif fw.soa:
        writer.warn("no soa.csv in export; the Statement of Applicability (clause 6.1.3 d) must be requested")

    description = fw.description["file"]
    if (root / description).exists():
        writer.set_description(load_yaml(root / description))
    else:
        writer.warn(f"no {description} in export; the organization must provide it ({fw.description['title'].lower()})")

    meta = {}
    if (root / "evidence.csv").exists():
        for m in read_csv(root / "evidence.csv"):
            meta[m["path"].strip("/")] = m

    for folder, kind in (("policies", "policy"), ("evidence", "evidence")):
        base = root / folder
        for path in sorted(p for p in base.rglob("*") if p.is_file() and not p.name.startswith(".")):
            rel = path.relative_to(root).as_posix()
            m = meta.get(rel, {})
            controls = m.get("controls", "").replace(",", " ").split()
            requirements = [x for x in m.get("requirements", "").replace(",", " ").split() if x in known]
            if kind == "evidence" and not controls and not requirements:
                first = path.relative_to(base).parts[0]
                if first in control_ids:
                    controls = [first]
                elif first in known:
                    requirements = [first]
            unknown = [c for c in controls if c not in control_ids]
            if unknown:
                writer.warn(f"{rel} references unknown controls {unknown}")
            writer.add_file(
                path,
                title=m.get("title") or path.stem.replace("_", " ").replace("-", " "),
                kind=m.get("kind") or kind,
                controls=[c for c in controls if c in control_ids],
                requirements=requirements,
                date=m.get("date") or None,
                obtained=m.get("obtained") or obtained_default,
                source_ref=rel,
            )
