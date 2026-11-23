#!/usr/bin/env python3
"""Fill an app assessment's workpapers, QA and findings from the fixture's truth.json.

    python evals/app/oracle.py <engagement-dir> <truth.json>

A pipeline smoke test, not an assessor: it knows the planted answers. Every unit is a
requirement assessed directly (no control matrix). It concludes on the evidence linked
to each requirement: a planted defect becomes a deviation, an answers-only requirement
is concluded `inquiry-only`, a requirement with other evidence is conforming, and one
with no evidence is not audited.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent.parent / "skills" / "compliance-app-assessment"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "scripts" / "engine"))

from core import Engagement, dump_json, sha256_file  # noqa: E402

TEXT = {
    "en": {
        "inquiry": "Asked the developer how the requirement is met.",
        "inspect": "Inspected the code, configuration and documents linked to {req} to determine whether it is met as of the assessment date.",
        "attr": "{req} is met as of the assessment date",
        "design": "The configuration and documents show how {req} is addressed.",
        "answer_only": "Only the organization's answer supports {req}; no configuration, code or document was available to verify it.",
        "none": "No evidence was available for this requirement as of the assessment date.",
        "statement": "{req} is not met. {note}.",
        "objective": "{note} (evidence {ev}).",
        "limits_inquiry": "{n} requirements are supported only by the organization's answers and are not verified: {ids}.",
        "limits_none": "{n} requirements could not be assessed because no evidence was available.",
        "summary": ("The app has significant weaknesses: a privileged database key is shipped to every browser, row-level security is missing on a "
                    "table with health data, and identity documents are stored in a public bucket. They must be fixed before the app processes "
                    "personal data for the client's customers."),
        "response": "The developer has removed the service-role key and rotated it; the other items are scheduled.",
    },
    "de": {
        "inquiry": "Den Entwickler befragt, wie die Anforderung erfüllt wird.",
        "inspect": "Code, Konfiguration und Dokumente zu {req} eingesehen, um festzustellen, ob die Anforderung zum Stichtag erfüllt ist.",
        "attr": "{req} ist zum Stichtag erfüllt",
        "design": "Konfiguration und Dokumente zeigen, wie {req} umgesetzt ist.",
        "answer_only": "Nur die Angabe der Organisation stützt {req}; keine Konfiguration, kein Code und kein Dokument lag zur Verifizierung vor.",
        "none": "Für diese Anforderung lag zum Stichtag kein Nachweis vor.",
        "statement": "{req} ist nicht erfüllt. {note}.",
        "objective": "{note} (Nachweis {ev}).",
        "limits_inquiry": "{n} Anforderungen beruhen nur auf Angaben der Organisation und sind nicht verifiziert: {ids}.",
        "limits_none": "{n} Anforderungen konnten mangels Nachweisen nicht bewertet werden.",
        "summary": ("Die App weist erhebliche Schwachstellen auf: Ein privilegierter Datenbankschlüssel wird an jeden Browser ausgeliefert, für eine "
                    "Tabelle mit Gesundheitsdaten fehlt die zeilenbasierte Zugriffskontrolle, und Ausweisdokumente liegen in einem öffentlichen Bucket. "
                    "Sie müssen behoben werden, bevor die App personenbezogene Daten für die Kunden des Auftraggebers verarbeitet."),
        "response": "Der Entwickler hat den Service-Role-Schlüssel entfernt und rotiert; die übrigen Punkte sind eingeplant.",
    },
}


def main(root: str, truth_path: str) -> None:
    eng = Engagement(root)
    lang = eng.language
    T = TEXT[lang]
    truth = json.loads(Path(truth_path).read_text())
    defects = {d["requirement"]: d for d in truth["defects"]}
    inquiry_only = set(truth["inquiry_only"])
    arts = eng.manifest["artifacts"]
    unverified, missing = [], []

    for cid, wp in eng.load_workpapers().items():
        req = wp["criteria"][0]
        if (wp.get("prepared_by") or "").startswith("draft"):
            missing.append(req)  # draft closed it: no evidence linked (an agent leaves these alone too)
            continue
        linked = [a for a in arts if req in (a.get("requirements") or [])]
        answers = [a["id"] for a in linked if a["obtained"] == "inquiry"]
        evidence = [a["id"] for a in linked if a["obtained"] != "inquiry"]
        wp["deviations"], wp["procedures"] = [], [{"method": "inquiry", "text": T["inquiry"]}]
        if req in inquiry_only:
            wp["design"] = {"effective": True, "rationale": T["answer_only"].format(req=req), "evidence": answers}
            wp["attributes"] = {}
            wp["conclusion"] = "inquiry-only"
            unverified.append(req)
        elif not evidence:
            wp["design"] = {"effective": True, "rationale": T["none"], "evidence": answers}
            wp["attributes"] = {}
            wp["conclusion"] = "not-audited"
            wp["scope_limitation"] = T["none"]
            missing.append(req)
        else:
            wp["procedures"].append({"method": "inspection", "text": T["inspect"].format(req=req)})
            wp["design"] = {"effective": True, "rationale": T["design"].format(req=req), "evidence": evidence[:3]}
            wp["attributes"] = {"A": T["attr"].format(req=req)}
            d = defects.get(req)
            for item in wp["items"]:
                item["evidence"] = evidence
                item["results"] = {"A": "fail" if d else "pass"}
                if d:
                    wp["deviations"].append({"item": item["id"], "description": (d["note_de"] if lang == "de" else d["note"]) + ".", "evidence": evidence})
            wp["conclusion"] = "deviations" if wp["deviations"] else "conforming"
        wp["confidence"] = "high"
        wp["prepared_by"] = "oracle (evals/app/oracle.py)"
        dump_json(wp, eng.workpaper_path(cid))

    reviews = [{"control_id": cid, "workpaper_sha256": sha256_file(eng.workpaper_path(cid)), "verdict": "agree", "issues": [],
                "evidence_checked": [], "reviewed_by": "oracle"} for cid in eng.load_workpapers()]
    dump_json({"schema_version": 1, "reviews": reviews}, eng.qa_path)

    workpapers = eng.load_workpapers()
    findings = []
    for i, d in enumerate(sorted(truth["defects"], key=lambda x: (x["grade"] != "major", x["id"])), 1):
        cid = next(c for c, w in workpapers.items() if w["criteria"] == [d["requirement"]])
        dev = workpapers[cid]["deviations"][0]
        note = d["note_de"] if lang == "de" else d["note"]
        findings.append({"id": f"{'OFI' if d['grade'] == 'ofi' else 'NC'}-{i:02d}", "grade": d["grade"], "requirement": d["requirement"],
                         "statement": T["statement"].format(req=d["requirement"], note=note),
                         "objective_evidence": T["objective"].format(note=note, ev=", ".join(dev["evidence"])),
                         "deviations": [{"control": cid, "item": dev["item"]}], "evidence": dev["evidence"],
                         "management_response": T["response"] if i == 1 else None})
    limits = []
    if unverified:
        limits.append(T["limits_inquiry"].format(n=len(unverified), ids=", ".join(sorted(unverified))))
    if missing:
        limits.append(T["limits_none"].format(n=len(missing)))
    dump_json({"schema_version": 1, "findings": findings, "scope_limitations": limits, "recommendation": "not-recommended",
               "summary": T["summary"], "scope_appropriate": True, "scope_note": "", "prepared_by": "oracle"}, eng.findings_path)
    print(f"Oracle filled {len(reviews)} workpapers ({len(unverified)} answers only, {len(missing)} without evidence) in {eng.root}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
