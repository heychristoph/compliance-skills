# Copied from shared/engines/requirements/render.py by tools/sync.py. Edit that file, not this copy.
"""`render`: build the report PDF, workpaper spreadsheet and evidence index from the workpapers.

All report text comes from assets/report/text/<language>.yaml plus the validated
workpapers, findings and ISMS description. Nothing is written freehand here, so
the PDF cannot disagree with the work behind it.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import shutil
import tempfile
from pathlib import Path

from common import i18n
from core import APPLICABILITY, ASSETS, CLI, ENGINE, PROFILE, AuditError, Engagement, dump_json, fmt_date, load_catalog, load_json, load_yaml, parse_date
from review import signed_off, validate
import privacy

GRADE_ORDER = {"major": 0, "minor": 1, "ofi": 2}


def load_text(lang: str) -> dict:
    """Report wording for one language: assets/report/text/<lang>.yaml."""
    path = ASSETS / "report" / "text" / f"{lang}.yaml"
    if not path.exists():
        raise AuditError(f"No report text for language '{lang}' ({path}).")
    return load_yaml(path)


# Labels the Typst layout prints, passed through data.json.
TYPST_LABELS = ("header", "footer_final", "footer_draft", "page_of", "kicker", "not_official", "scope_label", "signed_by",
                "watermark", "contents", "section", "finding", "response")


class _Keep(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render(eng: Engagement) -> dict:
    errors, warnings = validate(eng, final=True)
    if errors:
        raise AuditError("Fix validation errors before rendering:\n  " + "\n  ".join(errors[:30]))
    final = signed_off(eng)
    text = load_text(eng.language)
    data = _report_data(eng, text, final)
    eng.report.mkdir(parents=True, exist_ok=True)
    stem = f"{PROFILE['report_stem']}-{eng.audit_type}-{re.sub(r'[^a-z0-9]+', '-', eng.config['organization'].lower()).strip('-')}"
    pdf = eng.report / f"{stem}{'' if final else '-DRAFT'}.pdf"
    _compile_pdf(data, pdf)
    dump_json(data, eng.report / "report-data.json")
    xlsx = eng.report / "workpapers.xlsx"
    _write_xlsx(eng, xlsx, text["labels"]["xlsx"])
    index = eng.report / "evidence-index.csv"
    _write_evidence_index(eng, index)
    if (PROFILE.get("report") or {}).get("annexes"):
        _write_annex_files(eng, data, text)
    return {"pdf": pdf, "xlsx": xlsx, "evidence_index": index, "final": final, "warnings": warnings}


# --- report content --------------------------------------------------------------


def _fill(s: str, v: _Keep) -> str:
    for _ in range(3):  # placeholders can contain placeholders
        s = s.format_map(v)
    s = re.sub(r"(?<!\.)\.\.(?!\.)", ".", s)  # "Inc." at the end of a sentence
    return " ".join(s.split())


class _Results:
    """What the audit concluded about each requirement, from workpapers and findings."""

    def __init__(self, eng: Engagement, findings: list[dict], L: dict):
        self.eng = eng
        self.L = L
        self.workpapers = eng.load_workpapers()
        self.findings = findings
        self.surveillance = eng.partial

    def units(self, req_id: str) -> list[dict]:
        return [wp for _, wp in sorted(self.workpapers.items()) if req_id in wp["criteria"]]

    def direct(self, req_id: str) -> list[dict]:
        """Findings recorded against this requirement."""
        return [f for f in self.findings if f["requirement"] == req_id]

    def related(self, req_id: str) -> list[dict]:
        """Findings recorded against another requirement that grade a deviation in a unit mapped to this one."""
        ids = {wp["control_id"] for wp in self.units(req_id)}
        return [f for f in self.findings if f["requirement"] != req_id and any(d["control"] in ids for d in f["deviations"])]

    def label(self, findings: list[dict]) -> str:
        ordered = sorted(findings, key=lambda f: (GRADE_ORDER[f["grade"]], f["id"]))
        short = self.L["grade_short"]
        return ", ".join(f["id"] if f["grade"] == "ofi" else f"{f['id']} ({short[f['grade']]})" for f in ordered)

    def result(self, req_id: str, labels: dict) -> tuple[str, bool]:
        """Short result for a requirement and whether a nonconformity is recorded against it."""
        units = self.units(req_id)
        direct = self.direct(req_id)
        related = [f for f in self.related(req_id) if f["grade"] != "ofi"]
        see = self.L["see"].format(ids=", ".join(f["id"] for f in related)) if related else ""
        ncs = [f for f in direct if f["grade"] != "ofi"]
        if ncs:
            return self.label(ncs) + see, True
        if not units:
            return (labels["not_sampled"] if self.surveillance else labels["not_audited"]), False
        if all(wp["conclusion"] in ("not-audited", "inquiry-only") for wp in units):
            if any(wp["conclusion"] == "inquiry-only" for wp in units):
                return labels["inquiry_only"] + see, False
            return labels["not_audited"] + see, False
        ofis = [f for f in direct if f["grade"] == "ofi"]
        return labels["conforming"] + (f"; {self.label(ofis)}" if ofis else "") + see, False


def _report_data(eng: Engagement, text: dict, final: bool) -> dict:
    doc = load_json(eng.findings_path)
    cfg = eng.config
    lang = eng.language
    L = text["labels"]
    catalog = load_catalog(lang)
    reqs = {r["id"]: r for r in catalog["requirements"]}
    std = text["standards"]
    atype = text["audit_types"][eng.audit_type]
    s1, s3 = text["section1"], text["section3"]
    signoff = cfg.get("signoff") or {}
    model = (signoff.get("model") or "").strip()
    if not model or not signoff.get("date"):
        raise AuditError(f"Run `{CLI} signoff --model \"<model name>\"` before render. The report is signed with that model name, the title AI Auditor, and the date of the signature.")
    report_date = fmt_date(parse_date(signoff["date"]), lang)
    mgmt = cfg.get("management") or {}
    representative = f"{str(mgmt.get('name') or '').strip()}, {str(mgmt.get('title') or '').strip()}"
    isms = privacy.report_description(eng) or {}
    findings = sorted(doc["findings"], key=lambda f: (GRADE_ORDER[f["grade"]], f["id"]))
    results = _Results(eng, findings, L)
    # Section V lists the Statement of Applicability's controls (ISO Annex A) or, for frameworks
    # scoped by role or entity type, every requirement with its applicability.
    soa_cfg = APPLICABILITY.get("soa")
    annex = [r for r in catalog["requirements"] if (r["kind"] == soa_cfg["kind"] if soa_cfg else True)]
    applicable = [r for r in annex if eng.applicable(r)]
    sampled = [r for r in applicable if results.units(r["id"])]
    start, end = eng.period
    counts = {g: sum(f["grade"] == g for f in findings) for g in GRADE_ORDER}
    soa_version = str(isms.get("soa_version") or "").strip()
    dates = {"date": fmt_date(end, lang), "start": fmt_date(start, lang), "end": fmt_date(end, lang)}

    v = _Keep(
        org=cfg["organization"], scope=cfg["scope"].strip(), model=model, representative=representative,
        type_label=atype["label"],
        period=L["period"]["stage1" if eng.point_in_time else "other"].format(**dates),
        period_dates=L["period_dates"]["stage1" if eng.point_in_time else "other"].format(**dates),
        standard=std["short"], standard_full=std["full"], certification=std["certification"],
        scope_values=i18n.join([L.get("scope_values", {}).get(x, x) for x in eng.scope_values], lang),
        soa_version=f" ({soa_version})" if soa_version else "",
        applicable=str(len(applicable)), excluded=str(len(annex) - len(applicable)), sampled=str(len(sampled)),
        majors=str(counts["major"]), minors=str(counts["minor"]), ofis=str(counts["ofi"]),
    )
    f = lambda s: _fill(s, v)

    # Section I: the report and its conclusion, signed by the model.
    facts = s1["facts"]
    b = [{"kind": "para", "text": f(s1["notice"] if signoff.get("model") else s1["notice_unsigned"])},
         {"kind": "para", "text": f(s1["addressee"])},
         {"kind": "heading", "text": s1["facts_heading"]},
         {"kind": "facts", "rows": [
             [facts["organization"], cfg["organization"]],
             [facts["representative"], representative],
             [facts["audit_type"], atype["label"]],
             [facts["criteria"], f(s1["criteria"])],
             [facts["records"], f(f"{atype['period_heading']} {{period_dates}}")],
             [facts["method"], facts["method_value"]],
             [facts["auditor"], L["auditor_line"].format(model=model)],
         ]},
         {"kind": "heading", "text": s1["objectives_heading"]}, {"kind": "para", "text": s1["objectives_intro"]},
         {"kind": "list", "items": [f(x) for x in atype["objectives"]]},
         {"kind": "heading", "text": s1["scope_heading"]}, {"kind": "para", "text": f(s1["scope"])},
         {"kind": "para", "text": f(s1["coverage"]["surveillance" if eng.partial else "full"])},
         {"kind": "heading", "text": s1["method_heading"]}, {"kind": "para", "text": f(s1["method"])}, {"kind": "para", "text": f(s1["sampling"])},
         {"kind": "heading", "text": s1["summary_heading"]}, {"kind": "para", "text": f(s1["summary_counts"])},
         {"kind": "list", "items": [s1["grades"][g] for g in GRADE_ORDER]}]
    if eng.point_in_time:
        b.append({"kind": "para", "text": s1["stage1_grades"]})
    if (PROFILE.get("report") or {}).get("evidence_strength"):
        b.append({"kind": "para", "text": _fill(L["strength"], _Keep(v, **evidence_strength(eng, results)))})
    b += [{"kind": "heading", "text": s1["conformity_heading"]}, {"kind": "para", "text": doc["summary"].strip()}]
    # Requirements the report states a result for in Section I (ISO: internal audit and management review).
    highlights = [(h["key"], [x for x in h["requirements"] if any(r["id"] == x for r in eng.requirements)])
                  for h in (PROFILE.get("report") or {}).get("highlights") or []]
    items = [_fill(s1["highlights"][key], _Keep(v, result=results_text(results, ids, text))) for key, ids in highlights if ids]
    if items:
        b += [{"kind": "heading", "text": s1["highlights_heading"]}, {"kind": "list", "items": items}]
    b += [
          {"kind": "heading", "text": s1["scope_appropriate_heading"]},
          {"kind": "para", "text": f(s1["scope_appropriate"]["yes" if doc["scope_appropriate"] else "no"]) + (" " + doc["scope_note"].strip() if (doc.get("scope_note") or "").strip() else "")},
          {"kind": "heading", "text": s1["objectives_met_heading"]},
          {"kind": "para", "text": f(s1["objectives_met"]["no" if doc["scope_limitations"] else "yes"])}]
    if doc["scope_limitations"]:
        b += [{"kind": "heading", "text": s1["limitations_heading"]}, {"kind": "list", "items": [x.strip() for x in doc["scope_limitations"]]}]
    b += [{"kind": "heading", "text": s1["recommendation_heading"]},
          {"kind": "para", "text": f(s1["recommendation"][eng.audit_type][doc["recommendation"]]), "strong": True},
          {"kind": "para", "text": f(s1["ai_disclaimer"])},
          {"kind": "heading", "text": s1["independence_heading"]}, {"kind": "para", "text": f(s1["independence"])},
          {"kind": "heading", "text": s1["restricted_use_heading"]}, {"kind": "para", "text": f(s1["restricted_use"])},
          {"kind": "signature", "lines": [model, L["signer_title"], report_date, s1["signature_footer"]]}]
    section1 = {"title": f(s1["title"]), "blocks": b}

    # Section II: the organization's own description of its ISMS.
    s2 = text["section2"]
    blocks = []
    if not isms:
        blocks.append({"kind": "para", "text": f(s2["omitted"])})
    else:
        blocks.append({"kind": "para", "text": f(s2["intro"])})
        if isms.get("status") != "management-approved":
            blocks.append({"kind": "para", "text": f(s2["unapproved"])})
        for key, heading in s2["headings"].items():
            value = isms.get(key)
            if value:
                blocks.append({"kind": "heading", "text": f(heading)})
                blocks += _prose(value)
    section2 = {"title": f(s2["title"]), "blocks": blocks}

    # Section III: graded findings.
    labels = s3["labels"]
    section3 = {"title": f(s3["title"]), "intro": f(s3["intro_stage1"] if eng.point_in_time else s3["intro"]), "none": s3["none"], "findings": [
        {"id": x["id"], "grade": x["grade"], "grade_name": s3["grade_names"][x["grade"]],
         "rows": [[labels["requirement"], f"{x['requirement']} {reqs[x['requirement']]['title']}"],
                  [labels["statement_ofi"] if x["grade"] == "ofi" else labels["statement"], x["statement"].strip()],
                  [labels["evidence"], x["objective_evidence"].strip()]]
                 + ([[labels["units"], ", ".join(sorted({d["control"] for d in x["deviations"]}))]] if x["deviations"] else [])}
        for x in findings]}

    # Section IV: every requirement in scope, the units that address it, and results.
    s4 = text["section4"]
    groups = []
    for code, title in catalog["groups"].items():
        rows = []
        for req in eng.requirements:
            if req["group"] != code:
                continue
            units = results.units(req["id"])
            rows.append({"id": req["id"], "title": req["title"], **({"maps": _crosswalk(req, L)} if (PROFILE.get("report") or {}).get("crosswalk") else {}), "units": [_unit_row(eng, wp, s4, results, L) for wp in units]
                         or [{"control": "—", "activity": "", "tests": [], "result": s4["not_sampled"] if results.surveillance else s4["not_audited"].format(reason=""), "flag": False}]})
        if rows:
            groups.append({"title": (L["clause_group"].format(code=code, title=title) if not code.startswith(tuple((PROFILE.get("report") or {}).get("plain_group_prefixes") or [])) else title), "rows": rows})
    section4 = {"title": f(s4["title"]), "intro": [f(s4["intro"]), f(s4["methods"])], "columns": s4["columns"], "groups": groups}

    # Section V: applicability (the Statement of Applicability, or scope by role or entity type) and the result.
    s5 = text["section5"]
    res = s5["results"]
    soa = eng.soa or {}
    soa_rows = []
    for r in annex:
        row = soa.get(r["id"]) or {}
        ok, why = eng.applicability(r)
        if ok:
            result, flag = results.result(r["id"], res)
            soa_rows.append({"id": r["id"], "title": r["title"], "applicable": L["yes"], "justification": "", "result": result, "flag": flag})
        else:
            reason = (privacy.redact((row.get("justification") or "").strip(), eng) or L["no_justification"]) if why == "soa" \
                else _fill(L["excluded"][why], v)
            soa_rows.append({"id": r["id"], "title": r["title"], "applicable": L["no"], "justification": reason,
                             "result": res["excluded"], "flag": False})
    missing_soa = bool(soa_cfg) and eng.soa is None
    section5 = {"title": f(s5["title"]), "intro": f(s5["missing"] if missing_soa else s5["intro"]), "columns": s5["columns"], "rows": soa_rows}

    # Section VI: the organization's response.
    s6 = text["section6"]
    responses = [{"finding": x["id"], "grade_name": s3["grade_names"][x["grade"]], "statement": x["statement"].strip(), "response": x["management_response"].strip()}
                 for x in findings if (x.get("management_response") or "").strip()]
    section6 = {"title": f(s6["title"]), "intro": f(s6["intro"]), "responses": responses, "none": s6["none"]}

    cover = text["cover"]
    return {
        "final": final,
        "lang": L["lang"], "paper": L["paper"], "labels": {k: L[k] for k in TYPST_LABELS + ("annex",) if k in L},
        "draft_note": L["draft_note"].format(generated=dt.date.today().isoformat()),
        "org": cfg["organization"], "scope": cfg["scope"].strip(), "auditor": L["auditor"],
        "model": model, "signer_name": model, "signer_title": L["signer_title"], "report_date": report_date,
        "type_label": atype["label"], "period": f(f"{atype['period_heading']} {{period_dates}}"),
        "title": f(cover["title"]), "disclaimer": f(cover["disclaimer"]), "restricted": f(cover["restricted"]),
        "counts": counts, "recommendation": doc["recommendation"],
        "generated": dt.date.today().isoformat(),
        "sections": [section1, section2], "section3": section3, "section4": section4, "section5": section5, "section6": section6,
        **({"annexes": _annexes(eng, text, results, v)} if (PROFILE.get("report") or {}).get("annexes") else {}),
    }


TIERS = ("direct", "captured", "client", "inquiry")


def evidence_strength(eng: Engagement, results: "_Results") -> dict[str, str]:
    """How each requirement in scope was verified: the strongest evidence tier its units cite.

    Counts per tier, plus `none` for requirements no unit assessed (not audited, or no workpaper)."""
    from review import _cited

    counts = dict.fromkeys(TIERS + ("none",), 0)
    for req in eng.requirements:
        tiers = set()
        for wp in results.units(req["id"]):
            if wp["conclusion"] in ("not-audited", "pending"):
                continue
            tiers |= {eng.artifacts[i].get("obtained", "client") for i in _cited(wp) if i in eng.artifacts}
        counts[next((t for t in TIERS if t in tiers), "none")] += 1
    return {k: str(n) for k, n in counts.items()}


def results_text(results: _Results, req_ids: list[str], text: dict) -> str:
    """One sentence on a clause for Section I (internal audit, management review)."""
    labels = text["section5"]["results"]
    C = text["labels"]["clause_result"]
    direct = {f["id"]: f for rid in req_ids for f in results.direct(rid) if f["grade"] != "ofi"}
    if direct:
        return C["nonconforming"].format(ids=results.label(list(direct.values())))
    related = {f["id"]: f for rid in req_ids for f in results.related(rid) if f["grade"] != "ofi"}
    states = [results.result(rid, labels)[0].split(";")[0] for rid in req_ids]
    if all(s == labels["conforming"] for s in states):
        tail = C["related"].format(ids=results.label(list(related.values()))) if related else ""
        return C["conforming"] + tail
    lower = text["labels"]["lowercase_states"]
    return "; ".join(f"{rid} {s.lower() if lower else s}" for rid, s in zip(req_ids, states)) + "."


def _unit_row(eng: Engagement, wp: dict, s4: dict, results: _Results, L: dict) -> dict:
    tests = [p["text"] for p in wp["procedures"]]
    plan = wp["plan"]
    if plan["population"] and plan["population"]["size"] > 1:
        tests.append(L["sample"].format(sample=plan["sample_size"], population=plan["population"]["size"]))
    concl = wp["conclusion"]
    linked = [f for f in results.findings if any(d["control"] == wp["control_id"] for d in f["deviations"])]
    if concl == "conforming":
        result = s4["conforming"]
    elif concl == "not-audited":
        result = _fill(s4["not_audited"], _Keep(reason=wp.get("scope_limitation") or ""))
    elif concl == "inquiry-only":
        result = s4["inquiry_only"]
    elif concl == "design-gap":
        result = _fill(s4["design_gap"], _Keep(reason=wp["design"]["rationale"]))
    else:
        result = " ".join(x["description"] for x in wp["deviations"] if x["item"] != "design")
    if linked and concl != "conforming":
        result += L["see_sentence"].format(ids=", ".join(x["id"] for x in sorted(linked, key=lambda x: x["id"])))
    flag = concl in ("deviations", "design-gap") and any(x["grade"] != "ofi" for x in linked)
    return {"control": wp["control_id"], "activity": privacy.activity(eng, wp), "tests": tests, "result": result.strip(), "flag": flag}


def _prose(value) -> list[dict]:
    """Turn a description value (text, list of text, or list of named entries) into report blocks."""
    if isinstance(value, str):
        return [{"kind": "para", "text": " ".join(p.split())} for p in value.split("\n\n") if p.strip()]
    if isinstance(value, list) and all(isinstance(x, dict) for x in value):
        items = []
        for x in value:
            name = x.get("name") or x.get("title") or ""
            rest = "; ".join(str(v) for k, v in x.items() if k not in ("name", "title") and v and not isinstance(v, (list, dict)))
            items.append(f"{name}: {rest}" if name and rest else name or rest)
        return [{"kind": "list", "items": items}]
    if isinstance(value, list):
        return [{"kind": "list", "items": [str(x) for x in value]}]
    if isinstance(value, dict):
        return [{"kind": "list", "items": [f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in value.items() if v]}]
    return [{"kind": "para", "text": str(value)}]


# --- PDF -------------------------------------------------------------------------


def _crosswalk(req: dict, L: dict) -> str:
    """The provisions of other frameworks a requirement supports (profile report.crosswalk), e.g. "GDPR Art.32(1)(b) · NIS2 Art.21(2)(i)"."""
    shown = (PROFILE.get("report") or {}).get("crosswalk") or []
    names = L.get("crosswalk_names") or {}
    parts = [f"{names.get(fw, fw.upper())} {', '.join(req['maps'][fw])}" for fw in shown if (req.get("maps") or {}).get(fw)]
    return " · ".join(parts)


def _annexes(eng: Engagement, text: dict, results: "_Results", v) -> list[dict]:
    """Annex A, the measures actually verified (for a DPA's technical and organizational measures annex);
    Annex B, the sub-processors found in the stack and the description."""
    A = text["annex"]
    L = text["labels"]
    tiers = L["tier_names"]
    prefixes = tuple((PROFILE.get("report") or {}).get("measures_groups") or ["SEC"])
    from review import _cited

    measures = []
    for req in eng.requirements:
        if not str(req.get("group", "")).startswith(prefixes):
            continue
        result, flag = results.result(req["id"], text["section5"]["results"])
        found = set()
        for wp in results.units(req["id"]):
            if wp["conclusion"] not in ("not-audited", "pending"):
                found |= {eng.artifacts[i].get("obtained", "client") for i in _cited(wp) if i in eng.artifacts}
        tier = next((t for t in TIERS if t in found), "none")
        measures.append({"cells": [req["id"], req["title"], result, tiers[tier]], "flag": flag})
    subs = _subprocessors(eng)
    return [
        {"title": _fill(A["measures"]["title"], v), "intro": _fill(A["measures"]["intro"], v), "columns": A["measures"]["columns"],
         "widths": [2.2, 6.0, 3.6, 3.2], "rows": measures, "none": A["measures"]["none"]},
        {"title": _fill(A["subprocessors"]["title"], v), "intro": _fill(A["subprocessors"]["intro"], v), "columns": A["subprocessors"]["columns"],
         "widths": [3.6, 6.4, 5.0], "rows": [{"cells": [s["name"], s["service"], s["dpa"] or "—"], "flag": False} for s in subs],
         "none": A["subprocessors"]["none"]},
    ]


def _subprocessors(eng: Engagement) -> list[dict]:
    """Sub-processors from stack detection (review/stack.yaml) and the organization's description (outsourced)."""
    out: dict[str, dict] = {}
    stack = eng.review / "stack.yaml"
    if stack.exists():
        for s in load_yaml(stack).get("subprocessors") or []:
            out[s["name"]] = {"name": s["name"], "service": s.get("service") or "", "dpa": s.get("dpa") or ""}
    for o in (privacy.report_description(eng) or {}).get("outsourced") or []:
        if isinstance(o, dict) and o.get("name"):
            out.setdefault(o["name"], {"name": o["name"], "service": o.get("service") or o.get("services") or "", "dpa": o.get("dpa") or ""})
    return sorted(out.values(), key=lambda s: s["name"].lower())


def _write_annex_files(eng: Engagement, data: dict, text: dict) -> None:
    """Editable copies next to the PDF: the annexes (to attach to a DPA) and the fixes list, in the report language."""
    for annex, name in zip(data["annexes"], ("annex-measures.md", "annex-subprocessors.md")):
        lines = [f"# {annex['title']}", "", annex["intro"], "", "| " + " | ".join(annex["columns"]) + " |", "|" + "---|" * len(annex["columns"])]
        lines += ["| " + " | ".join(str(c).replace("|", "/") for c in r["cells"]) + " |" for r in annex["rows"]] or [annex["none"]]
        (eng.report / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    F = text["fixes"]
    doc = load_json(eng.findings_path)
    lines = [f"# {F['title']}", "", F["intro"], ""]
    for grade in ("major", "minor", "ofi"):
        items = sorted((x for x in doc["findings"] if x["grade"] == grade), key=lambda x: x["id"])
        if items:
            lines += [f"## {F['grades'][grade]}", ""]
            lines += [f"- **{x['id']}** ({x['requirement']}): {x['statement'].strip()}" for x in items]
            lines.append("")
    unverified = sorted(cid for cid, wp in eng.load_workpapers().items() if wp.get("conclusion") == "inquiry-only")
    if unverified:
        lines += [f"## {F['unverified']}", ""] + [f"- {cid}" for cid in unverified] + [""]
    (eng.report / "fixes.md").write_text("\n".join(lines), encoding="utf-8")


def _compile_pdf(data: dict, out: Path) -> None:
    try:
        import typst
    except ImportError as e:
        raise AuditError("The `typst` Python package is required: pip install -r scripts/requirements.txt") from e
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copyfile(ENGINE / "report.typ", Path(tmp) / "report.typ")
        shutil.copyfile(ASSETS / "report" / "logo.svg", Path(tmp) / "logo.svg")
        dump_json(data, Path(tmp) / "data.json")
        typst.compile(str(Path(tmp) / "report.typ"), output=str(out))


# --- spreadsheet and index -----------------------------------------------------------


def _write_xlsx(eng: Engagement, path: Path, X: dict) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = X["sheets"]["units"]
    ws.append(X["units"])
    samples = wb.create_sheet(X["sheets"]["samples"])
    samples.append(X["samples"])
    devs = wb.create_sheet(X["sheets"]["deviations"])
    devs.append(X["deviations"])
    for cid, wp in sorted(eng.load_workpapers().items()):
        p = wp["plan"]
        ws.append([cid, " ".join(wp["criteria"]), p["frequency"], p["nature"],
                   f"{p['population']['source']} ({p['population']['size']})" if p["population"] else "",
                   p["sample_size"], wp["design"]["effective"], wp["conclusion"], len(wp["deviations"]),
                   wp.get("confidence"), wp.get("prepared_by"), privacy.activity(eng, wp)])
        for item in wp["items"]:
            samples.append([cid, item["id"], ", ".join(f"{k}={r}" for k, r in sorted(item["results"].items())),
                            " ".join(item["evidence"]), item.get("note", "")])
        for x in wp["deviations"]:
            devs.append([cid, x["item"], x["description"], " ".join(x["evidence"])])
    fs = wb.create_sheet(X["sheets"]["findings"])
    fs.append(X["findings"])
    doc = load_json(eng.findings_path)
    for x in doc["findings"]:
        fs.append([x["id"], x["grade"], x["requirement"], x["statement"], x["objective_evidence"],
                   " ".join(f"{d['control']}/{d['item']}" for d in x["deviations"]), " ".join(x["evidence"]), x.get("management_response") or ""])
    soa = wb.create_sheet(X["sheets"]["soa"])
    soa.append(X["soa"])
    workpapers = eng.load_workpapers()
    soa_cfg = APPLICABILITY.get("soa")
    for r in load_catalog()["requirements"]:
        if soa_cfg and r["kind"] != soa_cfg["kind"]:
            continue
        row = (eng.soa or {}).get(r["id"]) or {}
        soa.append([r["id"], X["yes"] if eng.applicable(r) else X["no"], privacy.redact(row.get("justification") or "", eng), row.get("status") or "",
                    " ".join(cid for cid, wp in sorted(workpapers.items()) if r["id"] in wp["criteria"])])
    ev = wb.create_sheet(X["sheets"]["evidence"])
    ev.append(X["evidence"])
    for a in eng.manifest["artifacts"]:
        ev.append([a["id"], privacy.redact(a["title"], eng), a["kind"], privacy.redact(a["path"], eng), a["sha256"], a["obtained"], a.get("date", ""),
                   " ".join(a.get("controls", [])), " ".join(a.get("requirements", []))])
    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
    wb.save(path)


def _write_evidence_index(eng: Engagement, path: Path) -> None:
    cited = {}
    for cid, wp in eng.load_workpapers().items():
        ids = set(wp["design"]["evidence"]) | {e for i in wp["items"] for e in i["evidence"]} | {e for x in wp["deviations"] for e in x["evidence"]}
        if wp.get("population_check"):
            ids |= set(wp["population_check"]["evidence"])
        for e in ids:
            cited.setdefault(e, []).append(cid)
    for x in load_json(eng.findings_path)["findings"]:
        for e in x["evidence"]:
            cited.setdefault(e, []).append(x["id"])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "title", "kind", "path", "sha256", "obtained", "date", "cited_by"])
        for a in eng.manifest["artifacts"]:
            w.writerow([a["id"], privacy.redact(a["title"], eng), a["kind"], privacy.redact(a["path"], eng), a["sha256"], a["obtained"], a.get("date", ""),
                        " ".join(sorted(set(cited.get(a["id"], []))))])
