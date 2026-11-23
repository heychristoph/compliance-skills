"""Score a finished app assessment against the fixture's planted defects.

Deterministic: reads the engagement folder only, so it grades any agent or model.
Beyond the defects it checks what this skill adds: stack detection, the code scan,
evidence tiers, answers-only requirements reported as not verified, the
evidence-strength summary, the role-based scope, and the annexes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent.parent / "skills" / "compliance-app-assessment"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "scripts" / "engine"))

from core import Engagement, load_json  # noqa: E402
from review import validate  # noqa: E402

FLAGGED = ("deviations", "design-gap")


def grade(root: Path, truth: dict) -> dict:
    eng = Engagement(root)
    results = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        results.append({"check": name, "passed": bool(passed), "detail": detail})

    errors, _ = validate(eng, final=True) if eng.testplan_path.exists() else (["no test plan"], [])
    check("validate --final passes", not errors, "; ".join(errors[:3]))
    check("report rendered", any(eng.report.glob("*.pdf")) if eng.report.exists() else False)
    check("review packet written", (eng.review / "packet.md").exists())
    data_path = eng.report / "report-data.json"
    data = json.loads(data_path.read_text()) if data_path.exists() else {}
    check("report in the engagement language", data.get("lang") == eng.language, f"report {data.get('lang')}, engagement {eng.language}")

    stack = yaml.safe_load((eng.review / "stack.yaml").read_text()) if (eng.review / "stack.yaml").exists() else {}
    found = {c["component"] for c in stack.get("components") or []}
    check("detect found the stack", set(truth["components"]) <= found, f"found {sorted(found)}")
    rules = {f["rule"] for f in stack.get("scan_findings") or []}
    check("code scan found the planted code issues", set(truth["scan_rules"]) <= rules, f"found {sorted(rules)}")
    subs = {s["name"] for s in stack.get("subprocessors") or []}
    check("sub-processors identified", set(truth["subprocessors"]) <= subs, f"found {sorted(subs)}")

    probe = next((a for a in (eng.manifest["artifacts"] if eng.manifest_path.exists() else []) if (a.get("capture") or {}).get("via") == "probe"), None)
    summary = json.loads((eng.bundle / probe["path"]).read_text())["summary"] if probe else {}
    check("probe proved anonymous access", summary.get("tables_readable_by_anyone") == truth["probe"]["tables"]
          and summary.get("buckets_listable_by_anyone") == truth["probe"]["buckets"], json.dumps(summary))
    probe_text = (eng.bundle / probe["path"]).read_text() if probe else ""
    check("probe read no data", "passport-0001" not in probe_text, "a file name from the bucket leaked into the evidence")
    tiers = {a["obtained"] for a in eng.manifest["artifacts"]} if eng.manifest_path.exists() else set()
    check("every evidence tier present", {"direct", "captured", "client", "inquiry"} <= tiers, f"found {sorted(tiers)}")

    wps = eng.load_workpapers() if eng.workpapers.exists() else {}
    by_req = {w["criteria"][0]: w for w in wps.values() if w.get("criteria")}
    doc = load_json(eng.findings_path) if eng.findings_path.exists() else {}
    findings = doc.get("findings", [])
    for d in truth["defects"]:
        wp = by_req.get(d["requirement"])
        check(f"{d['id']}: {d['requirement']} flagged", bool(wp) and wp["conclusion"] in FLAGGED, d["note"])
        graded = any(f["requirement"] == d["requirement"] and f["grade"] in ("major", "minor") for f in findings)
        check(f"{d['id']}: graded as a nonconformity", graded)
    drafted = [w for w in wps.values() if (w.get("prepared_by") or "").startswith("draft")]
    check("draft closed units with no evidence", bool(drafted) and all(w["conclusion"] == "not-audited" for w in drafted), f"{len(drafted)} drafted")
    for req in truth["inquiry_only"]:
        wp = by_req.get(req)
        check(f"{req}: answers only, reported as not verified", bool(wp) and wp["conclusion"] == "inquiry-only")
    for req in truth["out_of_scope"]:
        check(f"{req}: out of scope for this role", req not in by_req)

    s1 = json.dumps((data.get("sections") or [{}])[0])
    check("evidence-strength summary in Section I", any(w in s1 for w in ("answers only", "nur Angaben", "Angaben", "answers")), "")
    files = {p.name for p in eng.report.glob("*.md")} if eng.report.exists() else set()
    check("annexes and fixes list written", {"annex-measures.md", "annex-subprocessors.md", "fixes.md"} <= files, f"found {sorted(files)}")
    annex_b = (eng.report / "annex-subprocessors.md").read_text() if (eng.report / "annex-subprocessors.md").exists() else ""
    check("sub-processor annex lists the providers", all(n in annex_b for n in truth["subprocessors"]))
    check("recommendation in acceptable set", doc.get("recommendation") in truth["acceptable_recommendations"], f"got {doc.get('recommendation')}")

    passed = sum(r["passed"] for r in results)
    return {"score": round(passed / len(results), 3), "passed": passed, "total": len(results), "checks": results}


def print_grade(g: dict) -> None:
    for r in g["checks"]:
        print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['check']}" + (f"  ({r['detail']})" if r["detail"] and not r["passed"] else ""))
    print(f"  score {g['score']} ({g['passed']}/{g['total']})")


if __name__ == "__main__":
    print_grade(grade(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())))
