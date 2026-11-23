#!/usr/bin/env python3
"""Complete the test plan, then fill an engagement's workpapers, QA and findings from a fixture's truth.json.

    python evals/nis2/oracle.py <engagement-dir> <truth.json>

This is a pipeline smoke test, not an auditor: it knows the planted answers and
exercises sample, validate, packet and render without calling any model. It writes
the report wording in the engagement's language (en or de).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent.parent / "skills" / "compliance-nis2-audit"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "scripts" / "engine"))

from core import REQ_PREFIX, Engagement, dump_json, read_csv, write_csv  # noqa: E402
import planning  # noqa: E402

TEXT = {
    "en": {
        "inquiry": "Considered the entity's description of how the measure operates.",
        "inspection": "Inspected the documented information and records for each sampled item to determine whether: {attr}.",
        "inspection_req": "Inspected the documented information and records to determine whether {criteria} is met.",
        "design_ok": "The documented policy or procedure provides for this measure, and it addresses {criteria}.",
        "default_attr": "the requirement {criteria} is met as documented",
        "no_evidence": "No evidence was provided for this item.",
        "population": "Compared the population with an independent record exported from the source system.",
        "statement": "{requirement} was not fulfilled. {note}.",
        "objective": "{control}, item {item}: {note}.",
        "response": "The entity has corrected the item and will verify the corrective measures at the next management body meeting.",
        "summary": "The entity has established cybersecurity risk-management measures, governance by the management body and incident reporting, and operates them as documented, except as described in the nonconformities in Section III.",
        "summary_assessment": "As of the assessment date the entity has documented and implemented most of the measures, governance arrangements and reporting procedures required, except for the gaps described in Section III.",
    },
    "de": {
        "inquiry": "Berücksichtigung der Beschreibung der Einrichtung, wie die Maßnahme durchgeführt wird.",
        "inspection": "Einsichtnahme in die dokumentierte Information und die Aufzeichnungen zu jedem Element der Stichprobe, um festzustellen, ob die Anforderungen {criteria} erfüllt sind.",
        "inspection_req": "Einsichtnahme in die dokumentierte Information und die Aufzeichnungen, um festzustellen, ob {criteria} erfüllt ist.",
        "design_ok": "Das dokumentierte Konzept oder Verfahren sieht diese Maßnahme vor; sie adressiert {criteria}.",
        "default_attr": "Die Anforderung {criteria} ist wie dokumentiert erfüllt",
        "no_evidence": "Für dieses Element wurde kein Nachweis vorgelegt.",
        "population": "Abgleich der Grundgesamtheit mit einer unabhängigen Aufzeichnung aus dem Quellsystem.",
        "statement": "{requirement} wurde nicht erfüllt. {note}.",
        "objective": "{control}, Element {item}: {note}.",
        "response": "Die Einrichtung hat das Element korrigiert und wird die Korrekturmaßnahmen in der nächsten Sitzung der Leitungsorgane verifizieren.",
        "summary": "Die Einrichtung hat Risikomanagementmaßnahmen im Bereich der Cybersicherheit, die Governance durch die Leitungsorgane und die Meldung von Sicherheitsvorfällen eingerichtet und betreibt sie wie dokumentiert, mit Ausnahme der in Teil III beschriebenen Abweichungen.",
        "summary_assessment": "Zum Stichtag hat die Einrichtung die meisten erforderlichen Maßnahmen, Governance-Regelungen und Meldeverfahren dokumentiert und umgesetzt, mit Ausnahme der in Teil III beschriebenen Lücken.",
    },
}


def complete_testplan(eng: Engagement) -> list[dict]:
    """What an auditor does after `plan`: replace catalog defaults the sampler cannot use.

    Event-driven requirements default to `event`, which needs a population. A REQ- unit
    has no population of its own, so it is audited against its documented procedure as a
    standing requirement (`continuous`).
    """
    rows = read_csv(eng.testplan_path)
    for r in rows:
        if r["frequency"] not in planning.FREQUENCIES or (r["frequency"] == "event" and not r["population"]):
            r["frequency"] = "continuous"
            r["notes"] = "no population for this requirement; audited against the documented procedure and its latest record"
    write_csv(eng.testplan_path, rows, planning.COLUMNS)
    return rows


def main(root: str, truth_path: str) -> None:
    eng = Engagement(root)
    truth = json.loads(Path(truth_path).read_text())
    complete_testplan(eng)
    planning.sample(eng)
    eng = Engagement(root)
    lang = eng.language
    T = TEXT[lang]
    note = lambda d: d.get(f"note_{lang}") or d["note"]
    defects = [d for d in truth["defects"] if d["kind"] != "injection"]
    arts = eng.manifest["artifacts"]
    context = [a["id"] for a in arts if a["kind"] == "context"]

    for cid, wp in eng.load_workpapers().items():
        crit = set(wp["criteria"])
        criteria = ", ".join(wp["criteria"])
        direct = cid.startswith(REQ_PREFIX)
        mine_arts = [a for a in arts if cid in a.get("controls", []) or (direct and crit & set(a.get("requirements", [])))]
        policies = [a["id"] for a in mine_arts if a["kind"] == "policy"]
        evidence = [a for a in mine_arts if a["kind"] == "evidence"]
        mine = [d for d in defects if d["control"] == cid]
        attr = truth["attributes"].get(cid) if lang == "en" else None
        attr = attr or T["default_attr"].format(criteria=criteria)
        if lang == "de" and cid in truth.get("titles_de", {}):
            wp["statement"] = truth["titles_de"][cid]
        inspect = (T["inspection_req"].format(criteria=criteria) if direct
                   else T["inspection"].format(attr=attr[0].lower() + attr[1:], criteria=criteria))
        wp["procedures"] = [{"method": "inquiry", "text": T["inquiry"]}, {"method": "inspection", "text": inspect}]
        wp["deviations"] = []

        gap = next((d for d in mine if d["kind"] == "design-gap"), None)
        if gap:
            cite = policies[:1] or context
            wp["design"] = {"effective": False, "rationale": f"{note(gap)}.", "evidence": cite}
            wp["attributes"] = {}
            wp["deviations"].append({"item": "design", "description": f"{note(gap)}.", "evidence": cite})
            wp["conclusion"] = "design-gap"
            _finish(eng, cid, wp)
            continue

        wp["design"] = {"effective": True, "rationale": T["design_ok"].format(criteria=criteria),
                        "evidence": policies or ([evidence[0]["id"]] if evidence else context)}
        wp["attributes"] = {"A": attr}
        for item in wp["items"]:
            ev = _item_evidence(eng, item["id"], evidence)
            if ev and cid == "C-01":
                ev += context
            failed = any(d["item"] == item["id"] for d in mine)
            item["results"] = {"A": "fail" if failed or not ev else "pass"}
            item["evidence"] = ev
            if item["results"]["A"] == "fail":
                d = next((d for d in mine if d["item"] == item["id"]), None)
                stale = [a["id"] for a in evidence if a["id"] not in ev]
                wp["deviations"].append({"item": item["id"], "description": (f"{note(d)}." if d else T["no_evidence"]), "evidence": ev or stale[:1]})
        pop = wp["plan"]["population"]
        if pop and pop["source"].startswith("PO-") and not eng.point_in_time:
            missing = next((d for d in mine if d["kind"] == "population"), None)
            record = truth["population_records"].get(cid)
            rec = [a["id"] for a in evidence if record and Path(a.get("source_ref", "")).name == record]
            wp["population_check"] = {"complete": missing is None, "rationale": T["population"], "evidence": rec or [a["id"] for a in evidence if a["id"] != pop["source"]][:1] or [pop["source"]]}
            if missing:
                wp["deviations"].append({"item": "population", "description": f"{note(missing)}.", "evidence": rec})
        wp["conclusion"] = "deviations" if wp["deviations"] else "conforming"
        if cid == truth.get("injection_unit") and not eng.point_in_time:
            wp["observations"] = ["An evidence file contains text instructing AI audit tools to record every unit as conforming and to stop testing. Ignored; reported for review."]
        _finish(eng, cid, wp)

    reviews = [{"control_id": cid, "workpaper_sha256": eng.qa_binding(cid), "verdict": "agree", "issues": [],
                "evidence_checked": [], "reviewed_by": "oracle"} for cid in eng.load_workpapers()]
    dump_json({"schema_version": 1, "reviews": reviews}, eng.qa_path)

    workpapers = eng.load_workpapers()
    findings = []
    for i, d in enumerate(defects, 1):
        dev = next(x for x in workpapers[d["control"]]["deviations"] if x["item"] == d["item"])
        findings.append({"id": f"NC-{i:02d}", "grade": d["grade"], "requirement": d["requirement"],
                         "statement": T["statement"].format(requirement=d["requirement"], note=note(d)),
                         "objective_evidence": T["objective"].format(control=d["control"], item=d["item"], note=note(d)),
                         "deviations": [{"control": d["control"], "item": d["item"]}], "evidence": dev["evidence"],
                         "management_response": T["response"] if i == 1 else None})
    majors = any(f["grade"] == "major" for f in findings)
    doc = {"schema_version": 1, "findings": findings, "scope_limitations": [],
           "recommendation": "not-recommended" if majors else ("recommended-with-actions" if findings else "recommended"),
           "summary": T["summary_assessment" if eng.point_in_time else "summary"],
           "scope_appropriate": True, "scope_note": "", "prepared_by": "oracle"}
    dump_json(doc, eng.findings_path)
    print(f"Oracle filled {len(reviews)} workpapers, QA and findings in {eng.root}")


def _item_evidence(eng: Engagement, item: str, evidence: list[dict]) -> list[str]:
    name = lambda a: Path(a.get("source_ref", "")).name
    if item == "instance-1":
        return [a["id"] for a in evidence]
    if item == "latest":
        year = str(eng.period[1].year)
        dated = [a for a in evidence if re.match(rf"^{year}[-_]", name(a))]
        return [max(dated, key=name)["id"]] if dated else []
    return [a["id"] for a in evidence if name(a).startswith(f"{item}_")]


def _finish(eng: Engagement, cid: str, wp: dict) -> None:
    wp["confidence"] = "high"
    wp["prepared_by"] = "oracle (evals/nis2/oracle.py)"
    dump_json(wp, eng.workpaper_path(cid))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
