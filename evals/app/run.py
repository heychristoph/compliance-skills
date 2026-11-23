#!/usr/bin/env python3
"""Run the app assessment on a fixture with any agent, then grade the result.

    python evals/app/run.py --case processor --agent oracle
    python evals/app/run.py --case developer --agent oracle --language de
    python evals/app/run.py --case processor --agent 'claude -p --permission-mode bypassPermissions {prompt}'

`--agent oracle` replays the recorded captures and fills workpapers from the known
answers: a model-free regression test of detect, capture, intake, the evidence tiers,
the not-verified conclusion, the annexes and the report. A real agent gets the app
repository and the recorded captures folder in place of live MCP servers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent / "skills" / "compliance-app-assessment"
APP = [sys.executable, str(SKILL / "scripts" / "app.py")]
sys.path.insert(0, str(HERE))

from graders import grade, print_grade  # noqa: E402

PROMPT = """Assess the security and data processing of the app in {engagement}/app, following the skill at {skill}.
The engagement folder {engagement} already has engagement.yaml and context.yaml. There are no live MCP servers:
the results of the Supabase MCP calls, the user's exports and the user's answers are recorded in {engagement}/captures
and described in {engagement}/captures.yaml. Use them in place of live calls (capture each one), run detect on the
repository, and complete the assessment through render and packet. Sign with the model name that did the work.
Use {python} to run the scripts."""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", default="processor", choices=["processor", "developer"])
    p.add_argument("--agent", required=True, help="'oracle' or a command template containing {prompt}")
    p.add_argument("--language", choices=["en", "de"], help="report language for this run (default en)")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--timeout", type=int, default=4 * 3600)
    a = p.parse_args()
    fixture = HERE / "fixtures" / a.case
    if not fixture.exists():
        sys.exit(f"No fixture {fixture}. Run: python evals/app/make_fixture.py")
    truth = json.loads((fixture / "truth.json").read_text())
    scores = []
    for i in range(a.runs):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run = HERE / "runs" / f"{stamp}-{a.case}-{a.language or 'en'}-{i + 1}"
        shutil.copytree(fixture, run, ignore=shutil.ignore_patterns("truth.json"))
        _language(run, a.language or "en")
        print(f"run {i + 1}: {run}")
        if a.agent == "oracle":
            _oracle(run, fixture / "truth.json")
        else:
            prompt = PROMPT.format(engagement=run, skill=SKILL, python=sys.executable)
            cmd = [prompt if tok == "{prompt}" else tok for tok in shlex.split(a.agent)]
            with open(run / "agent.log", "w") as log:
                subprocess.run(cmd, cwd=run, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout)
        g = grade(run, truth)
        (run / "grade.json").write_text(json.dumps(g, indent=2) + "\n")
        print_grade(g)
        scores.append(g["score"])
    if len(scores) > 1:
        print(f"mean score {sum(scores) / len(scores):.3f} over {len(scores)} runs")
    return 0


def _language(run: Path, lang: str) -> None:
    cfg = yaml.safe_load((run / "engagement.yaml").read_text())
    cfg["language"] = lang
    de = run / "context.de.yaml"
    if lang == "de":
        ctx = yaml.safe_load(de.read_text())
        cfg["scope"] = ctx["scope_statement"]
        shutil.copyfile(de, run / "context.yaml")
    de.unlink()
    (run / "engagement.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))


def replay(run: Path) -> None:
    """Capture every recorded result, as an agent would after each MCP call, export or answer."""
    for c in yaml.safe_load((run / "captures.yaml").read_text()):
        cmd = APP + ["capture", str(run), "--via", c["via"], "--title", c["title"], "--by", "oracle replay"]
        for r in c.get("requirements") or []:
            cmd += ["--requirement", r]
        if c.get("recipe"):
            cmd += ["--recipe", c["recipe"]]
        if c["via"] == "mcp":
            cmd += ["--server", c["server"], "--tool", c["tool"], "--args", json.dumps(c.get("args") or {}), "--file", str(run / "captures" / c["file"])]
        elif c["via"] == "export":
            cmd += ["--file", str(run / "captures" / c["file"])]
        elif c["via"] == "answer":
            cmd += ["--question", c["question"], "--text", c["text"]]
        elif c["via"] == "cli":
            cmd += ["--", *c["command"]]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


class _MockSupabase(BaseHTTPRequestHandler):
    """The live API of the fixture project, as an anonymous visitor sees it: treatment_notes leaks, id-documents is listable."""
    COUNTS = {"bookings": 0, "treatment_notes": 42}
    BUCKETS = {"id-documents": [{"name": "passport-0001.pdf"}], "avatars": []}

    def _anon(self) -> bool:
        return self.headers.get("apikey", "").startswith("eyJ")

    def do_GET(self):
        if self.path.startswith("/rest/v1/") and self._anon():
            body = json.dumps({"paths": {f"/{t}": {} for t in self.COUNTS} | {"/rpc/get_stats": {}}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/openapi+json"); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(401); self.end_headers()

    def do_HEAD(self):
        table = self.path.split("/rest/v1/")[-1].split("?")[0]
        if table in self.COUNTS and self._anon() and self.headers.get("Prefer") == "count=exact":
            n = self.COUNTS[table]
            self.send_response(206 if n else 200); self.send_header("Content-Range", f"0-0/{n}" if n else "*/0"); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        bucket = self.path.split("/object/list/")[-1]
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if bucket in self.BUCKETS and self._anon():
            body = json.dumps(self.BUCKETS[bucket]).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(400); self.end_headers()

    def log_message(self, *args):
        pass


def _oracle(run: Path, truth_path: Path) -> None:
    step = lambda *args, ok=(0,): _step(APP + list(args), ok)
    step("detect", str(run), "--repo", str(run / "app"))
    replay(run)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockSupabase)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        step("probe", str(run), "supabase-anon", "--authorized", "--url", f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
    step("ingest", str(run))
    step("check", str(run))
    step("plan", str(run), ok=(0, 1))  # 1: rows need input; the next line gives it, as an auditor would
    _confirm_plan(run)
    step("sample", str(run))
    step("draft", str(run))
    subprocess.run([sys.executable, str(HERE / "oracle.py"), str(run), str(truth_path)], check=True, stdout=subprocess.DEVNULL)
    step("signoff", str(run), "--model", "oracle")
    step("render", str(run))
    step("packet", str(run))


def _confirm_plan(run: Path) -> None:
    """Event-driven requirements have no population in a point-in-time assessment: assess the procedure as it stands."""
    import csv

    path = run / "testplan.csv"
    rows = list(csv.DictReader(path.open()))
    for r in rows:
        if r["frequency"] == "event" and not r["population"]:
            r["frequency"], r["notes"] = "continuous", "no population at a point in time; the procedure and its latest record were assessed"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _step(cmd: list[str], ok=(0,)) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode not in ok:
        sys.exit(f"$ {' '.join(cmd[1:3])} failed ({r.returncode}):\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")


if __name__ == "__main__":
    sys.exit(main())
