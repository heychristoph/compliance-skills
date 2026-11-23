"""Evidence the agent gathers itself: capture, the intake connector, evidence tiers and several sources."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GDPR = ROOT / "skills" / "compliance-gdpr-audit" / "scripts" / "gdpr.py"
TEMPLATE = ROOT / "skills" / "compliance-prep" / "assets" / "folder-template"


def run(*cmd, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, input=stdin)


class Capture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.eng = self.tmp / "e"
        r = run(sys.executable, GDPR, "init", self.eng, "--org", "Example GmbH", "--scope", "The Example app.", "--type", "assessment",
                "--roles", "processor", "--as-of", "2026-11-23", "--connector", "intake")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def capture(self, *args, stdin=None):
        r = run(sys.executable, GDPR, "capture", self.eng, *args, stdin=stdin)
        return r

    def manifest(self) -> dict:
        return json.loads((self.eng / "bundle" / "manifest.json").read_text())

    def test_every_route_gets_its_tier(self):
        self.assertEqual(self.capture("--via", "mcp", "--server", "supabase", "--tool", "get_advisors", "--args", '{"type": "security"}',
                                      "--title", "Security advisors", "--requirement", "Art.32(1)(b)", stdin='[{"name": "rls_disabled"}]').returncode, 0)
        self.assertNotEqual(self.capture("--via", "cli", "--title", "Python version", "--", "git", "--version").returncode, 0,
                         "git --version is not a listed read-only form")
        r = self.capture("--via", "cli", "--title", "Inside a git checkout", "--cwd", str(ROOT), "--", "git", "rev-parse", "--is-inside-work-tree")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        shot = self.tmp / "shot.png"
        shot.write_bytes(b"png")
        self.assertEqual(self.capture("--via", "export", "--file", shot, "--title", "Auth settings").returncode, 0)
        self.assertEqual(self.capture("--via", "answer", "--title", "Restore test", "--question", "Was a restore tested?",
                                      "--text", "No.", "--requirement", "Art.32(1)(c)").returncode, 0)
        r = run(sys.executable, GDPR, "ingest", self.eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tiers = {a["title"]: a["obtained"] for a in self.manifest()["artifacts"] if a["kind"] == "evidence"}
        self.assertEqual(tiers, {"Security advisors": "captured", "Inside a git checkout": "captured", "Auth settings": "client", "Restore test": "inquiry"})
        mcp = next(a for a in self.manifest()["artifacts"] if a["title"] == "Security advisors")
        self.assertEqual(mcp["capture"]["tool"], "get_advisors")
        self.assertEqual(mcp["requirements"], ["Art.32(1)(b)"])

    def test_mutating_commands_are_refused(self):
        for cmd in (["git", "push"], ["supabase", "db", "reset"], ["rm", "-rf", "x"], ["echo", "hi;", "ls"],
                    [sys.executable, "-c", "open('proof.txt', 'a').close()"], ["node", "-e", "1"], ["gh", "api", "-X", "DELETE", "repos/a/b"],
                    ["gh", "api", "repos/a/b/issues", "-f", "title=x"], ["git", "diff", "--ext-diff"], ["git", "log", "--output=x"],
                    ["git", "-c", "diff.external=x", "log"], ["supabase", "db", "dump", "-f", "out.sql"], ["npm", "audit", "fix"],
                    ["gh", "api", "repos/a/b/subscription", "-XDELETE"], ["git", "blame", "data.txt"], ["git", "diff"], ["git", "status"],
                    ["git", "--help", "log"], ["git", "-p", "log"], ["yarn", "audit"], ["pnpm", "audit"], ["gh", "repo", "view", "--web"],
                    ["gh", "api", "repos/a/b", "-iXDELETE"], ["gh", "api", "repos/a/b", "-if", "title=x"], ["gh", "api", "repos/a/b", "-H", "X-HTTP-Method-Override: DELETE"],
                    ["./git", "log"], ["/tmp/git", "log"], ["git", "log", "--show-signature"], ["git", "log", "--format=%G?"]):
            r = self.capture("--via", "cli", "--title", "x", "--", *cmd)
            self.assertNotEqual(r.returncode, 0, cmd)
        self.assertFalse((self.eng / "intake").exists() and list((self.eng / "intake").glob("*.meta.json")))

    def test_captures_are_never_overwritten(self):
        for _ in range(2):
            self.capture("--via", "answer", "--title", "Same title", "--question", "Q?", "--text", "A.")
        self.assertEqual(len(list((self.eng / "intake").glob("*.meta.json"))), 2)

    def test_intake_alone_gets_an_empty_control_matrix(self):
        self.capture("--via", "answer", "--title", "T", "--question", "Q?", "--text", "A.")
        r = run(sys.executable, GDPR, "ingest", self.eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("every requirement in scope is assessed directly", r.stdout)
        self.assertTrue((self.eng / "bundle" / "controls.csv").exists())


class Iteration(unittest.TestCase):
    """Re-running and rolling forward build on what exists instead of starting over."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.eng = self.tmp / "e"
        run(sys.executable, GDPR, "init", self.eng, "--org", "Example GmbH", "--scope", "The app.", "--type", "assessment",
            "--roles", "processor", "--as-of", "2026-11-23", "--connector", "intake")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ids(self) -> dict[str, str]:
        m = json.loads((self.eng / "bundle" / "manifest.json").read_text())
        return {a["title"]: a["id"] for a in m["artifacts"] if a["id"].startswith("EV-")}

    def test_unchanged_evidence_keeps_its_id_on_reingest(self):
        for title in ("First", "Second"):
            run(sys.executable, GDPR, "capture", self.eng, "--via", "answer", "--title", title, "--question", "Q?", "--text", "A.")
        run(sys.executable, GDPR, "ingest", self.eng)
        before = self.ids()
        # A new capture arrives, and an export is added; re-ingest.
        run(sys.executable, GDPR, "capture", self.eng, "--via", "answer", "--title", "Third", "--question", "Q?", "--text", "A.")
        r = run(sys.executable, GDPR, "ingest", self.eng, "--replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self.ids()
        self.assertEqual({k: after[k] for k in before}, before, "unchanged evidence keeps its ID")
        self.assertNotIn(after["Third"], before.values(), "new evidence gets a new ID")

    def test_retired_ids_are_never_reused(self):
        """EV-0001 disappears in one re-ingest; a later re-ingest must not give that ID to other evidence."""
        import sys as _s
        _s.path.insert(0, str(ROOT / "shared"))
        from lib.bundle import BundleWriter

        d = self.tmp / "b"
        first = BundleWriter(d / "1", "t")
        first.add_bytes("a", "a.txt", title="A", source_ref="a")
        m1 = first.finish()
        second = BundleWriter(d / "2", "t")
        second.keep_ids_from(m1)
        second.add_bytes("b", "b.txt", title="B", source_ref="b")   # A is gone, B is new
        m2 = second.finish()
        third = BundleWriter(d / "3", "t")
        third.keep_ids_from(m2)
        new = third.add_bytes("c", "c.txt", title="C", source_ref="c")
        self.assertNotIn(new, {"EV-0001", "EV-0002"}, "an ID used by an earlier ingest was reassigned")

    def test_rollforward_carries_settings_and_requires_followup(self):
        nxt = self.tmp / "next"
        (self.eng / "findings.json").write_text(json.dumps({"findings": [{"id": "F-01"}]}))
        r = run(sys.executable, GDPR, "rollforward", self.eng, nxt, "--as-of", "2027-05-01")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cfg = yaml.safe_load((nxt / "engagement.yaml").read_text())
        old = yaml.safe_load((self.eng / "engagement.yaml").read_text())
        self.assertEqual(cfg["as_of"], "2027-05-01")
        self.assertEqual(cfg["roles"], old["roles"])
        self.assertEqual(cfg["prior"], str(self.eng.resolve()))
        self.assertIsNone(cfg["signoff"])
        self.assertNotEqual(cfg["sampling_seed"], old["sampling_seed"])
        self.assertTrue((nxt / "prior" / "findings.json").exists())

    def test_draft_prefills_and_closes_units_without_evidence(self):
        import csv

        run(sys.executable, GDPR, "capture", self.eng, "--via", "answer", "--title", "Records of processing", "--question", "Q?",
            "--text", "Kept in the shared drive.", "--requirement", "Art.30(2)")
        run(sys.executable, GDPR, "ingest", self.eng)
        run(sys.executable, GDPR, "plan", self.eng)
        path = self.eng / "testplan.csv"
        rows = list(csv.DictReader(path.open()))
        for r in rows:
            if r["frequency"] == "event" and not r["population"]:
                r["frequency"] = "continuous"
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        self.assertEqual(run(sys.executable, GDPR, "sample", self.eng).returncode, 0)
        r = run(sys.executable, GDPR, "draft", self.eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Drafted 1 units", r.stdout)
        wp = json.loads((self.eng / "workpapers" / "REQ-Art.30_2_.json").read_text())
        self.assertEqual(wp["conclusion"], "pending")
        self.assertTrue(wp["design"]["evidence"] and wp["attributes"] and wp["procedures"])
        other = json.loads((self.eng / "workpapers" / "REQ-Art.32_1_.json").read_text())
        self.assertEqual(other["conclusion"], "not-audited")
        self.assertTrue(other["prepared_by"].startswith("draft"))
        pack = run(sys.executable, GDPR, "unit", self.eng, "REQ-Art.30(2)").stdout
        self.assertIn("Records of processing", pack)
        self.assertIn("Kept in the shared drive.", pack)
        r = run(sys.executable, GDPR, "validate", self.eng, "--unit", "REQ-Art.32(1)")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_status_notes_a_newer_skill(self):
        cfg = yaml.safe_load((self.eng / "engagement.yaml").read_text())
        cfg["tool_version"] = "0.0.1"
        (self.eng / "engagement.yaml").write_text(yaml.safe_dump(cfg))
        r = run(sys.executable, GDPR, "status", self.eng)
        self.assertIn("planned with 0.0.1", r.stdout)


class SeveralSources(unittest.TestCase):
    def test_records_plus_intake_share_one_bundle(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            records = tmp / "records"
            shutil.copytree(TEMPLATE, records)
            (records / "frameworks" / "gdpr.yaml").write_text(yaml.safe_dump(
                {"id": "gdpr", "name": "GDPR", "controls": [{"ref": "Art. 32", "name": "Security", "measures": ["mfa"]}]}))
            eng = tmp / "e"
            r = run(sys.executable, GDPR, "init", eng, "--org", "Example GmbH", "--scope", "The app.", "--type", "assessment",
                    "--roles", "processor", "--as-of", "2026-11-23", "--connector", "records", "--connector", "intake",
                    "--option", f"records.path={records}")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            cfg = yaml.safe_load((eng / "engagement.yaml").read_text())
            self.assertEqual([s["connector"] for s in cfg["sources"]], ["records", "intake"])
            self.assertEqual(cfg["sources"][0]["options"]["path"], str(records))
            run(sys.executable, GDPR, "capture", eng, "--via", "answer", "--title", "T", "--question", "Q?", "--text", "A.")
            r = run(sys.executable, GDPR, "ingest", eng)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            m = json.loads((eng / "bundle" / "manifest.json").read_text())
            self.assertEqual(m["connector"], "records+intake")
            ids = [a["id"] for a in m["artifacts"]]
            self.assertEqual(len(ids), len(set(ids)), "artifact IDs run on across sources")
            self.assertIn("inquiry", {a["obtained"] for a in m["artifacts"]})
            self.assertIn("mfa", (eng / "bundle" / "controls.csv").read_text())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
