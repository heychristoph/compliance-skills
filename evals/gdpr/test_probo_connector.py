#!/usr/bin/env python3
"""Exercise the Probo connector against a local mock of Probo's MCP API.

    python evals/gdpr/test_probo_connector.py

The mock serves the audit fixture in Probo's shapes (GDPR framework controls
named by article, measures, evidences, documents, people, third parties,
findings, audits, organization context) using the tool names and fields from
Probo's published MCP specification, then runs ingest, check and plan through
the real CLI. GDPR has no Statement of Applicability: the mock offers one, and
the connector must not pull it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "skills" / "compliance-gdpr-audit" / "scripts"))
sys.path.insert(0, str(HERE.parent.parent / "skills" / "compliance-gdpr-audit" / "scripts" / "engine"))

from core import dump_yaml, load_requirements, load_yaml, read_csv  # noqa: E402

TOKEN = "test-token"


def build_state(export: Path) -> dict:
    controls = read_csv(export / "controls.csv")
    meta = {m["path"]: m for m in read_csv(export / "evidence.csv")}
    ts = "2026-03-01T00:00:00Z"
    ids = [c["id"] for c in controls]
    # A GDPR framework in Probo: section_title is the article reference as people write it ("Art. 30(1)").
    state = {
        "requirements": [{"id": f"ctl_{r['id']}", "section_title": r["id"].replace("Art.", "Art. "), "name": r["title"]} for r in load_requirements()],
        "measures": {c["id"]: {"id": f"msr_{c['id']}", "name": c["title"], "description": c["description"], "category": "", "state": "IMPLEMENTED",
                               "created_at": ts, "updated_at": ts} for c in controls},
        "req_measures": {r["id"]: [c["id"] for c in controls if r["id"] in c["criteria"].split()] for r in load_requirements()},
        "evidences": {c["id"]: [] for c in controls},
        "files": {"/files/audit/internal-audit-report-2026.pdf": b"%PDF-INTERNAL-AUDIT"},
        "documents": {},
        "soa": [],
    }
    for path in sorted((export / "evidence").rglob("*")):
        if path.is_file() and path.parent.name in ids:
            cid = path.parent.name
            fid = f"file_{len(state['files'])}"
            state["files"][f"/files/{fid}/{path.name}"] = path.read_bytes()
            state["evidences"][cid].append({"id": f"evd_{fid}", "organization_id": "org_1", "measure_id": f"msr_{cid}", "state": "FULFILLED",
                                            "reference_id": path.name, "type": "FILE", "url": f"/files/{fid}/{path.name}", "description": path.stem,
                                            "created_at": ts, "updated_at": ts})
    for path in sorted((export / "policies").glob("*.md")):
        m = meta[f"policies/{path.name}"]
        doc = {"id": f"doc_{path.stem}", "controls": m["controls"].split(), "framework_controls": [],
               "title": m["title"].replace("Policy: ", ""), "content": path.read_text()}
        state["documents"][doc["id"]] = doc
    # One document hangs off a clause of the framework itself. The others hang off measures only.
    state["documents"]["doc_control_only"] = {
        "id": "doc_control_only", "controls": [], "framework_controls": ["ctl_Art.30(1)"],
        "title": "Control linked only", "content": "Direct framework-control link.",
    }
    pops = {n: read_csv(export / "populations" / f"{n}.csv") for n in ("hires", "terminations", "vendors", "incidents")}
    state["users"] = ([{"id": f"usr_{h['id']}", "full_name": h["name"], "email_address": "", "state": "ACTIVE", "contract": {"start": h["date"], "end": None}} for h in pops["hires"]]
                      + [{"id": f"usr_{t['id']}", "full_name": t["name"], "email_address": "", "state": "DEACTIVATED", "contract": {"start": "2023-01-09", "end": t["date"]}} for t in pops["terminations"]])
    state["vendors"] = [{"id": f"tp_{v['id']}", "name": v["name"], "category": v["service"], "created_at": v["date"] + "T00:00:00Z"} for v in pops["vendors"]]
    # Two incidents raised as minor nonconformities in Probo's findings register, plus an observation.
    state["findings"] = [{"id": f"fnd_{n['id']}", "organization_id": "org_1", "kind": "MINOR_NONCONFORMITY", "reference_id": n["id"], "description": n["summary"],
                          "source": "incident", "identified_on": n["date"], "status": "CLOSED", "priority": "MEDIUM", "created_at": ts, "updated_at": ts}
                         for n in pops["incidents"] if n["personal_data_breach"] == "yes"] + [{"id": "fnd_obs", "organization_id": "org_1", "kind": "OBSERVATION", "reference_id": "OBS-1",
                                                               "identified_on": "2026-02-01", "status": "OPEN", "priority": "LOW", "created_at": ts, "updated_at": ts}]
    state["context"] = load_yaml(export / "context.yaml")
    # Probo's MCP list leaves url empty for uploaded files. The file is only on the console GraphQL API.
    first = next(iter(state["evidences"]))
    state["files"]["/files/hidden/mfa-screenshot.png"] = b"PNG-MFA-SCREENSHOT"
    state["evidences"][first].append({
        "id": "evd_hidden", "organization_id": "org_1", "measure_id": f"msr_{first}", "state": "FULFILLED",
        "reference_id": "mfa-screenshot.png", "type": "FILE", "url": "", "description": "MFA screenshot",
        "created_at": ts, "updated_at": ts,
    })
    return state


def call_tool(state: dict, name: str, args: dict) -> dict:
    req_by_id = {r["id"]: r for r in state["requirements"]}
    if name == "listFrameworks":
        return {"frameworks": [{"id": "fw_iso", "organization_id": "org_1", "name": "ISO 27001 (2022)"}, {"id": "fw_gdpr", "organization_id": "org_1", "name": "GDPR"}]}
    if name == "listControls":
        return {"controls": state["requirements"]}
    if name == "listControlMeasures":
        req = req_by_id[args["control_id"]]["id"].removeprefix("ctl_")
        return {"measures": [state["measures"][cid] for cid in state["req_measures"][req]]}
    if name == "listStatementsOfApplicability":  # offered, but GDPR has no SoA and the connector must not ask
        return {"statements_of_applicability": [{"id": "soa_1", "organization_id": "org_1", "name": "Statement of Applicability v3", "document_id": None,
                                                 "created_at": "2026-03-02T00:00:00Z", "updated_at": "2026-03-02T00:00:00Z"}]}
    if name == "listApplicabilityStatements":
        return {"applicability_statements": state["soa"]}
    if name == "listFindings":
        return {"findings": state["findings"]}
    if name == "listAudits":
        return {"audits": [{"id": "aud_1", "organization_id": "org_1", "framework_id": "fw_gdpr", "name": "Internal data protection audit 2026", "firm": "Kanzlei Rehberg Datenschutz",
                            "validity": {"start": None, "end": None}, "audit_dates": {"start": "2026-05-11", "end": "2026-05-15"}, "state": "COMPLETED",
                            "has_report": True, "report_filename": "internal-audit-report-2026.pdf", "report_mime_type": "application/pdf"}]}
    if name == "getAuditReportUrl":
        return {"url": "/files/audit/internal-audit-report-2026.pdf"}
    if name in ("listTreatmentPlans", "listObligations", "listAssets", "listData"):
        return {{"listTreatmentPlans": "treatment_plans", "listObligations": "obligations", "listAssets": "assets", "listData": "data"}[name]: []}
    if name == "listMeasureEvidences":
        return {"evidences": state["evidences"][args["measure_id"].removeprefix("msr_")]}
    if name == "listControlDocuments":
        return {"documents": [{"id": d["id"]} for d in state["documents"].values() if args["control_id"] in d.get("framework_controls", [])]}
    if name == "listMeasureDocuments":
        cid = args["measure_id"].removeprefix("msr_")
        return {"documents": [{"id": d["id"]} for d in state["documents"].values() if cid in d["controls"]]}
    if name == "listDocumentVersions":
        d = state["documents"][args["document_id"]]
        return {"document_versions": [{"id": f"ver_{d['id']}", "status": "PUBLISHED", "major": 4, "minor": 2, "title": d["title"]}]}
    if name == "getDocumentVersion":
        d = state["documents"][args["id"].removeprefix("ver_")]
        return {"document_version": {"id": args["id"], "title": d["title"], "major": 4, "minor": 2, "status": "PUBLISHED", "content": d["content"], "published_at": "2026-01-15T00:00:00Z"}}
    if name == "listDocumentVersionSignatures":
        doc_id = args["document_version_id"].removeprefix("ver_")
        signer = state["users"][0]["id"]
        return {"document_version_signatures": [{"id": f"sig_{doc_id}", "document_version_id": args["document_version_id"],
                                                 "state": "SIGNED", "signed_by": signer, "signed_at": "2026-09-28T12:00:00Z"}]}
    if name == "listDocumentVersionApprovalQuorums":
        return {"approval_quorums": [{"id": "quorum_1", "status": "APPROVED", "version_id": args["document_version_id"]}]}
    if name == "listDocumentVersionApprovalDecisions":
        signer = state["users"][0]["id"]
        return {"approval_decisions": [{"id": "dec_1", "approver_id": signer, "state": "APPROVED", "decided_at": "2026-09-28T12:00:00Z"}]}
    if name == "listUsers":
        return {"users": state["users"]}
    if name == "listThirdParties":
        return {"thirdParties": state["vendors"]}
    if name == "listRisks":
        return {"risks": []}
    if name == "listAccessReviewCampaigns":
        return {"campaigns": [{"id": "camp_1", "name": "Initial Check", "status": "COMPLETED"}]}
    if name == "listAccessEntries":
        return {"entries": [{
            "source_name": "GitHub / example",
            "email": "a@example.com",
            "decision": "DEFER",
            "decision_note": "personal email, needs to change",
            "flags": [],
            "active": True,
        }]}
    if name == "listMeasureTasks":
        return {"tasks": [{"id": "task_1", "name": "Check MFA", "state": "DONE"}]}
    if name == "listTaskComments":
        return {"task_comments": [{"created_at": "2026-09-30T00:00:00Z", "content": "no email-and-password login"}]}
    if name == "getOrganizationContext":
        c = state["context"]
        return {"organization_context": {"product": c["services"], "customers": c["role"], "architecture": c["boundaries"],
                                         "team": c["people"], "processes": c["processes"]}}
    raise KeyError(name)


def serve(state: dict) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _auth(self) -> bool:
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                self.send_response(401)
                self.end_headers()
                return False
            return True

        def do_GET(self):
            if not self._auth():
                return
            body = state["files"].get(self.path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(body or b"")

        def do_POST(self):
            if not self._auth():
                return
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path.startswith("/api/console/v1/graphql"):
                found = req.get("variables", {}).get("id") == "evd_hidden"
                payload = {"data": {"node": {"file": {"fileName": "mfa-screenshot.png", "downloadUrl": "/files/hidden/mfa-screenshot.png"}}}} if found else {"errors": [{"message": "not found"}]}
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if "id" not in req:
                self.send_response(202)
                self.end_headers()
                return
            if req["method"] == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "mock-probo", "version": "0"}}
            else:
                try:
                    out = call_tool(state, req["params"]["name"], req["params"]["arguments"])
                    result = {"content": [{"type": "text", "text": json.dumps(out)}], "isError": False}
                except KeyError as e:
                    result = {"content": [{"type": "text", "text": f"unknown tool or id {e}"}], "isError": True}
            body = json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Mcp-Session-Id", "session-1")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    fixture = HERE / "fixtures" / "audit"
    if not fixture.exists():
        sys.exit("Run python evals/gdpr/make_fixture.py first.")
    server = serve(build_state(fixture / "export"))
    url = f"http://127.0.0.1:{server.server_address[1]}"
    gdpr = [sys.executable, str(HERE.parent.parent / "skills" / "compliance-gdpr-audit" / "scripts" / "gdpr.py")]
    with tempfile.TemporaryDirectory() as tmp:
        eng = Path(tmp) / "probo-engagement"
        eng.mkdir()
        cfg = load_yaml(fixture / "engagement.yaml")
        cfg["source"] = {"connector": "probo", "options": {"url": url, "organization_id": "org_1"}}
        dump_yaml(cfg, eng / "engagement.yaml")
        env = dict(os.environ, PROBO_TOKEN=TOKEN)
        ok = True
        for step in ("ingest", "check", "plan"):
            r = subprocess.run(gdpr + [step, str(eng)], env=env, capture_output=True, text=True)
            print(f"$ gdpr.py {step}\n" + "\n".join((r.stdout + r.stderr).strip().splitlines()[-12:]))
            if step != "plan" and r.returncode != 0:
                ok = False
                break
        if ok:
            manifest = json.loads((eng / "bundle" / "manifest.json").read_text())
            kinds = {}
            for art in manifest["artifacts"]:
                kinds[art["kind"]] = kinds.get(art["kind"], 0) + 1
            controls = read_csv(eng / "bundle" / "controls.csv")
            policy_arts = [a for a in manifest["artifacts"] if a["kind"] == "policy"]
            control_only = [a for a in policy_arts if a["title"] == "Policy: Control linked only"]
            policy_text = (eng / "bundle" / control_only[0]["path"]).read_text() if control_only else ""
            signer = read_csv(fixture / "export" / "populations" / "hires.csv")[0]["name"]
            signed = "SIGNED 2026-09-28" in policy_text and "APPROVED 2026-09-28" in policy_text and signer in policy_text
            control_only_reqs = control_only[0].get("requirements") == ["Art.30(1)"] if control_only else False
            review = next(eng.joinpath("bundle").rglob("*access-review-entries*.json"), None)
            review_ok = review is not None and "personal email, needs to change" in review.read_text()
            comments = list(eng.joinpath("bundle").rglob("*task-comments*.json"))
            comment_ok = any("no email-and-password login" in p.read_text() for p in comments)
            hidden = list((eng / "bundle" / "evidence").glob("*mfa-screenshot.png"))
            hidden_ok = len(hidden) == 1 and hidden[0].read_bytes() == b"PNG-MFA-SCREENSHOT"
            soa_ok = not (eng / "bundle" / "soa.csv").exists() and "soa" not in kinds
            context = load_yaml(eng / "bundle" / "context.yaml")
            context_ok = kinds.get("context") == 1 and context.get("status") == "draft" and "survey" in (context.get("services") or "")
            c06 = next(c for c in controls if c["title"] == "Data subject requests")
            mapping_ok = set(c06["criteria"].split()) == set(next(c for c in read_csv(fixture / "export" / "controls.csv") if c["id"] == "C-06")["criteria"].split())
            c02 = next(c for c in controls if c["title"] == "Data protection policy and accountability")
            mapping_ok = mapping_ok and set(c02["criteria"].split()) == {"Art.5(2)", "Art.24(1)", "Art.24(2)"}
            audit = [a for a in manifest["artifacts"] if a["path"].endswith("internal-audit-report-2026.pdf")]
            audit_ok = len(audit) == 1 and (eng / "bundle" / audit[0]["path"]).read_bytes() == b"%PDF-INTERNAL-AUDIT" and audit[0].get("requirements") == ["Art.24(1)", "Art.28(3)(h)", "Art.32(1)(d)"]
            ncs = read_csv(eng / "bundle" / "populations" / "nonconformities.csv")
            ncs_ok = len(ncs) == 2
            expected_files = sum(1 for p in (fixture / "export" / "evidence").rglob("*") if p.is_file() and p.parent.name.startswith("C-"))
            ok = (len(controls) == 22 and kinds.get("evidence", 0) >= expected_files and len(policy_arts) == 11
                  and kinds.get("population") == 4 and signed and control_only_reqs and hidden_ok
                  and review_ok and comment_ok and soa_ok and context_ok and mapping_ok and audit_ok and ncs_ok)
            print(f"controls={len(controls)} artifacts={kinds} signed={signed} doc-requirements={control_only_reqs} file={hidden_ok} review={review_ok} "
                  f"comments={comment_ok} no-soa={soa_ok} context={context_ok} mapping={mapping_ok} audit-report={audit_ok} nonconformities={ncs_ok} -> {'OK' if ok else 'UNEXPECTED'}")
    server.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
