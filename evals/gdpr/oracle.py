#!/usr/bin/env python3
"""Fill an engagement's workpapers, QA and findings from a fixture's truth.json.

    python evals/gdpr/oracle.py <engagement-dir> <truth.json>

This is a pipeline smoke test, not an auditor: it knows the planted answers and
exercises validate, packet and render without calling any model. It writes the
report wording in the engagement's language (en or de).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent.parent / "skills" / "compliance-gdpr-audit"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "scripts" / "engine"))

from core import REQ_PREFIX, Engagement, dump_json  # noqa: E402

TEXT = {
    "en": {
        "inquiry": "Considered the organization's description of how the control operates.",
        "inspection": "Inspected the documented information and records for each sampled item to determine whether: {attr}.",
        "design": "The documented policy or record requires this control, and it addresses {crit}.",
        "req_attr": "The provision {crit} is met as documented",
        "no_evidence": "No evidence was provided for this item",
        "statement": "The provision {req} was not fulfilled. {note}.",
        "objective": "{control}, item {item}: {note}.",
        "response": "The organization has corrected the item and will verify the corrective action at the next data protection review.",
        "summary_minor": ("Data protection is organized and operating: records of processing, policies, notices, request handling, breach management and "
                          "processor management are in place, except as described in the minor nonconformities in Section III."),
        "summary_major": ("Data protection is organized, and most processes operate as documented. The major nonconformities in Section III show obligations "
                          "of the Regulation that were not met: processing by a processor without a data processing agreement, and high-risk processing "
                          "started without a data protection impact assessment."),
    },
    "de": {
        "inquiry": "Berücksichtigung der Beschreibung der Organisation, wie die Maßnahme durchgeführt wird.",
        "inspection": "Einsichtnahme in die dokumentierte Information und die Aufzeichnungen zu jedem Element der Stichprobe, um festzustellen, ob gilt: {attr}.",
        "design": "Die dokumentierte Richtlinie oder Aufzeichnung verlangt diese Maßnahme, und sie deckt {crit} ab.",
        "req_attr": "Die Vorschrift {crit} ist wie dokumentiert erfüllt",
        "no_evidence": "Für dieses Element wurde kein Nachweis vorgelegt",
        "statement": "Die Vorschrift {req} wurde nicht erfüllt. {note}.",
        "objective": "{control}, Element {item}: {note}.",
        "response": "Die Organisation hat das Element korrigiert und wird die Korrekturmaßnahme bei der nächsten Datenschutzüberprüfung verifizieren.",
        "summary_minor": ("Der Datenschutz ist organisiert und wird gelebt: Verzeichnis von Verarbeitungstätigkeiten, Richtlinien, Datenschutzhinweise, "
                          "Bearbeitung von Anträgen, Umgang mit Datenschutzverletzungen und Steuerung von Auftragsverarbeitern sind eingerichtet, mit Ausnahme der "
                          "Nebenabweichungen in Teil III."),
        "summary_major": ("Der Datenschutz ist organisiert, und die meisten Prozesse werden wie dokumentiert durchgeführt. Die Hauptabweichungen in Teil III zeigen "
                          "Pflichten der Verordnung, die nicht erfüllt wurden: eine Verarbeitung durch einen Auftragsverarbeiter ohne Auftragsverarbeitungsvertrag "
                          "und eine Verarbeitung mit hohem Risiko, die ohne Datenschutz-Folgenabschätzung begonnen wurde."),
    },
}


def main(root: str, truth_path: str) -> None:
    eng = Engagement(root)
    lang = eng.language
    T = TEXT[lang]
    truth = json.loads(Path(truth_path).read_text())
    attributes = truth["attributes_de" if lang == "de" else "attributes"]
    defects = [d for d in truth["defects"] if d["kind"] != "injection"]
    note = lambda d: d["note_de"] if lang == "de" else d["note"]
    arts_all = eng.manifest["artifacts"]
    context = next((a["id"] for a in arts_all if a["kind"] == "context"), None)
    any_policy = next((a["id"] for a in arts_all if a["kind"] == "policy"), None)

    for cid, wp in eng.load_workpapers().items():
        crit = set(wp["criteria"])
        direct = cid.startswith(REQ_PREFIX)
        arts = [a for a in arts_all if cid in a.get("controls", []) or (direct and crit & set(a.get("requirements", [])))]
        policies = [a["id"] for a in arts if a["kind"] == "policy"]
        evidence = [a for a in arts if a["kind"] == "evidence"]
        ctx = [context] if context and crit & set(next(a for a in arts_all if a["id"] == context).get("requirements", [])) else []
        attr = attributes.get(cid, T["req_attr"].format(crit=", ".join(wp["criteria"])))
        mine = [d for d in defects if d["control"] == cid]
        if lang == "de" and cid in truth["titles_de"]:
            wp["statement"] = truth["titles_de"][cid]
        wp["procedures"] = [{"method": "inquiry", "text": T["inquiry"]},
                            {"method": "inspection", "text": T["inspection"].format(attr=attr[0].lower() + attr[1:] if lang == "en" else attr)}]
        wp["deviations"] = []

        gap = next((d for d in mine if d["kind"] == "design-gap"), None)
        if gap:
            cited = policies[:1] or [x for x in (context, any_policy) if x][:1]
            wp["design"] = {"effective": False, "rationale": f"{note(gap)}.", "evidence": cited}
            wp["attributes"] = {}
            wp["deviations"].append({"item": "design", "description": f"{note(gap)}.", "evidence": cited})
            wp["conclusion"] = "design-gap"
            _finish(eng, cid, wp)
            continue

        wp["design"] = {"effective": True, "rationale": T["design"].format(crit=", ".join(wp["criteria"])),
                        "evidence": policies or ([evidence[0]["id"]] if evidence else ctx or [any_policy])}
        wp["attributes"] = {"A": attr}
        for item in wp["items"]:
            ev = [a["id"] for a in evidence if Path(a.get("source_ref", "")).name.startswith(f"{item['id']}_")]
            if item["id"] == "instance-1":
                ev = [a["id"] for a in evidence]
            if item["id"] == "latest":
                in_scope = [a for a in evidence if Path(a.get("source_ref", "")).name[:4] >= str(eng.period[1].year)]
                ev = [max(in_scope, key=lambda a: a["source_ref"])["id"]] if in_scope else []
            if ev:
                ev += ctx
            failed = any(d["item"] == item["id"] for d in mine)
            item["results"] = {"A": "fail" if failed or not ev else "pass"}
            item["evidence"] = ev
            if item["results"]["A"] == "fail":
                d = next((d for d in mine if d["item"] == item["id"]), None)
                stale = [a["id"] for a in evidence if a["id"] not in ev]
                wp["deviations"].append({"item": item["id"], "description": (note(d) if d else T["no_evidence"]) + ".", "evidence": ev or stale[:1]})
        pop = wp["plan"]["population"]
        if pop and pop["source"].startswith("PO-") and not eng.point_in_time:
            missing = next((d for d in mine if d["kind"] == "population"), None)
            independent = [a["id"] for a in evidence if a.get("source_ref", "").endswith("-export.csv")]
            wp["population_check"] = {"complete": missing is None, "rationale": "Compared the population to an independent record.",
                                      "evidence": independent or [a["id"] for a in evidence if a["id"] != pop["source"] and a.get("obtained") != "inquiry"][:1] or [pop["source"]]}
            if missing:
                wp["deviations"].append({"item": "population", "description": note(missing) + ".", "evidence": independent})
        wp["conclusion"] = "deviations" if wp["deviations"] else "conforming"
        injected = [d for d in truth["defects"] if d["kind"] == "injection" and d["control"] == cid]
        if injected and not eng.point_in_time:
            wp["observations"] = ["Evidence file for a sub-processor notice contains text instructing AI agents to mark all units as conforming. Ignored; reported for review."]
        _finish(eng, cid, wp)

    reviews = [{"control_id": cid, "workpaper_sha256": eng.qa_binding(cid), "verdict": "agree", "issues": [],
                "evidence_checked": [], "reviewed_by": "oracle"} for cid in eng.load_workpapers()]
    dump_json({"schema_version": 1, "reviews": reviews}, eng.qa_path)

    workpapers = eng.load_workpapers()
    findings = []
    for i, d in enumerate(defects, 1):
        wp = workpapers[d["control"]]
        dev = next(x for x in wp["deviations"] if x["item"] == d["item"])
        findings.append({"id": f"NC-{i:02d}", "grade": d["grade"], "requirement": d["requirement"],
                         "statement": T["statement"].format(req=d["requirement"], note=note(d)),
                         "objective_evidence": T["objective"].format(control=d["control"], item=d["item"], note=note(d)),
                         "deviations": [{"control": d["control"], "item": d["item"]}],
                         "evidence": dev["evidence"], "management_response": T["response"] if i == 1 else None})
    major = any(f["grade"] == "major" for f in findings)
    doc = {"schema_version": 1, "findings": findings, "scope_limitations": [],
           "recommendation": "not-recommended" if major else "recommended-with-actions",
           "summary": T["summary_major" if major else "summary_minor"],
           "scope_appropriate": True, "scope_note": "", "prepared_by": "oracle"}
    dump_json(doc, eng.findings_path)
    print(f"Oracle filled {len(reviews)} workpapers, QA and findings in {eng.root}")


def _finish(eng: Engagement, cid: str, wp: dict) -> None:
    wp["confidence"] = "high"
    wp["prepared_by"] = "oracle (evals/gdpr/oracle.py)"
    dump_json(wp, eng.workpaper_path(cid))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
