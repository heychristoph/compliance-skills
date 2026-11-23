"""The audit skills read a compliance-prep records folder through the `records` connector."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "skills" / "compliance-prep" / "assets" / "folder-template"
SOC2 = ROOT / "skills" / "compliance-soc2-audit" / "scripts" / "soc2.py"
ISO = ROOT / "skills" / "compliance-iso27001-audit" / "scripts" / "iso27001.py"


def run(*cmd, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)


class RecordsConnector(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.records = self.tmp / "records"
        shutil.copytree(TEMPLATE, self.records)
        people = yaml.safe_load((self.records / "people.yaml").read_text())
        people.append({"id": "leaver", "name": "Dana Leaver", "email": "dana@example.com", "state": "INACTIVE",
                       "contract_start": "2025-01-01", "contract_end": "2026-03-15"})
        people.append({"id": "joiner", "name": "Sam Joiner", "email": "sam@example.com", "state": "ACTIVE", "contract_start": "2026-02-01"})
        (self.records / "people.yaml").write_text(yaml.safe_dump(people, sort_keys=False))
        (self.records / "documents").mkdir()
        (self.records / "documents" / "access-control-policy.md").write_text("Every admin account uses MFA.\n")
        iso = {"id": "iso-27001", "name": "ISO 27001 Criteria, AI Audited", "controls": [
            {"ref": "A.5.15", "name": "Access control", "measures": ["mfa"], "documents": ["access-control-policy"],
             "applicable": True, "justification": "In scope."},
            {"ref": "A.7.4", "name": "Physical security monitoring", "measures": [], "applicable": False,
             "justification": "No own premises; hosting provider."},
            {"ref": "9.2", "name": "Internal audit", "measures": ["scanning"]},
        ]}
        (self.records / "frameworks" / "iso-27001.yaml").write_text(yaml.safe_dump(iso, sort_keys=False))
        for args in (("init", "-q"), ("add", "."), ("-c", "user.name=Records Bot", "-c", "user.email=bot@example.com", "commit", "-qm", "records")):
            run("git", "-C", self.records, *args)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def manifest(self, eng: Path) -> dict:
        return json.loads((eng / "bundle" / "manifest.json").read_text())

    def test_soc2_engagement(self):
        eng = self.tmp / "soc2"
        r = run(sys.executable, SOC2, "init", eng, "--org", "Example Inc.", "--system", "Example", "--type", "2",
                "--start", "2026-01-01", "--end", "2026-06-30", "--connector", "records", "--option", f"path={self.records}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(sys.executable, SOC2, "ingest", eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = self.manifest(eng)
        self.assertEqual(m["connector"], "records")
        controls = (eng / "bundle" / "controls.csv").read_text()
        self.assertIn("mfa", controls)
        self.assertIn("CC6.1", controls)
        ev = [a for a in m["artifacts"] if a["path"].startswith("evidence/") and "mfa" in a["controls"]]
        self.assertTrue(ev, "evidence/mfa/* is linked to the mfa control")
        self.assertTrue(all(a.get("date") for a in ev), "evidence is dated by its git commit")
        self.assertTrue(all(a["obtained"] == "client" for a in m["artifacts"]))
        policy = next(a for a in m["artifacts"] if a["kind"] == "policy" and "Access Control" in a["title"])
        self.assertIn("Every admin account uses MFA.", (eng / "bundle" / policy["path"]).read_text())
        terms = (eng / "bundle" / "populations" / "terminations.csv").read_text()
        hires = (eng / "bundle" / "populations" / "hires.csv").read_text()
        self.assertIn("T-leaver", terms)
        self.assertIn("H-joiner", hires)
        self.assertTrue(any("git log" in a.get("source_ref", "") for a in m["artifacts"]), "change history exported")
        self.assertTrue((eng / "bundle" / "system.yaml").exists())
        r = run(sys.executable, SOC2, "check", eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_type1_keeps_events_up_to_the_as_of_date(self):
        eng = self.tmp / "type1"
        r = run(sys.executable, SOC2, "init", eng, "--org", "Example Inc.", "--system", "Example", "--type", "1",
                "--as-of", "2026-06-30", "--connector", "records", "--option", f"path={self.records}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(sys.executable, SOC2, "ingest", eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("H-joiner", (eng / "bundle" / "populations" / "hires.csv").read_text())
        self.assertIn("T-leaver", (eng / "bundle" / "populations" / "terminations.csv").read_text())

    def test_failed_replacement_keeps_the_previous_bundle(self):
        eng = self.tmp / "replace"
        run(sys.executable, SOC2, "init", eng, "--org", "Example Inc.", "--system", "Example", "--type", "1",
            "--as-of", "2026-06-30", "--connector", "records", "--option", f"path={self.records}")
        self.assertEqual(run(sys.executable, SOC2, "ingest", eng).returncode, 0)
        before = (eng / "bundle" / "manifest.json").read_text()
        shutil.rmtree(self.records / "frameworks")  # the source now fails
        r = run(sys.executable, SOC2, "ingest", eng, "--replace")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((eng / "bundle" / "manifest.json").read_text(), before, "the previous bundle stays in place")
        self.assertFalse((eng / "bundle.staging").exists())
        self.assertFalse(list(eng.glob("bundle.replaced-*")), "nothing is archived when the replacement fails")

    def test_changed_control_invalidates_its_tested_workpaper(self):
        eng = self.tmp / "changed"
        run(sys.executable, SOC2, "init", eng, "--org", "Example Inc.", "--system", "Example", "--type", "1",
            "--as-of", "2026-06-30", "--connector", "records", "--option", f"path={self.records}")
        run(sys.executable, SOC2, "ingest", eng)
        run(sys.executable, SOC2, "plan", eng)
        plan = eng / "testplan.csv"
        with plan.open() as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            row.update(frequency="annual", nature="manual")
        with plan.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        r = run(sys.executable, SOC2, "sample", eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        wp_path = eng / "workpapers" / "mfa.json"
        wp = json.loads(wp_path.read_text())
        wp["conclusion"] = "no-exceptions"
        wp_path.write_text(json.dumps(wp))
        measures = (self.records / "measures.yaml").read_text().replace("Every account with admin rights", "Every employee account", 1)
        (self.records / "measures.yaml").write_text(measures)
        r = run(sys.executable, SOC2, "ingest", eng, "--replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(sys.executable, SOC2, "sample", eng)
        self.assertNotEqual(r.returncode, 0, "a tested workpaper must not survive a changed control silently")
        self.assertIn("description or criteria changed", r.stdout + r.stderr)
        r = run(sys.executable, SOC2, "validate", eng)
        self.assertIn("description or criteria changed", r.stdout + r.stderr)

    def test_iso_engagement_prefers_ai_audited_framework_and_builds_soa(self):
        eng = self.tmp / "iso"
        r = run(sys.executable, ISO, "init", eng, "--org", "Example Inc.", "--scope", "The Example platform.", "--type", "stage2",
                "--start", "2026-01-01", "--end", "2026-06-30", "--connector", "records", "--option", f"path={self.records}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run(sys.executable, ISO, "ingest", eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        controls = (eng / "bundle" / "controls.csv").read_text()
        self.assertIn("A.5.15", controls)
        self.assertIn("9.2.1", controls, "clause 9.2 expands to 9.2.1 and 9.2.2")
        soa = (eng / "bundle" / "soa.csv").read_text()
        self.assertIn("A.7.4,no,No own premises", soa)
        self.assertTrue((eng / "bundle" / "isms.yaml").exists())
        r = run(sys.executable, ISO, "check", eng)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
