"""Checks on the shared parts: framework catalogs, translations, report wording and the sync step."""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FRAMEWORKS = ROOT / "shared" / "frameworks"
sys.path.insert(0, str(ROOT / "shared"))

from lib import i18n  # noqa: E402

# Catalog name -> key of its list of entries.
CATALOGS = {"soc2": "criteria", "iso27001": "requirements", "gdpr": "requirements", "nis2": "requirements", "app": "requirements"}
REPORT_TEXTS = sorted(ROOT.glob("skills/*/assets/report/text"))


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class Sync(unittest.TestCase):
    def test_copies_are_current(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "sync.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Catalogs(unittest.TestCase):
    def test_every_catalog_is_present(self):
        for name in CATALOGS:
            self.assertTrue((FRAMEWORKS / f"{name}.yaml").exists(), f"missing shared/frameworks/{name}.yaml")

    def test_entries_parse_cleanly(self):
        """An unquoted comma in a flow mapping silently splits a value into extra empty keys."""
        for name, key in CATALOGS.items():
            entries = _load(FRAMEWORKS / f"{name}.yaml")[key]
            ids = [str(e["id"]) for e in entries]
            self.assertEqual(len(ids), len(set(ids)), f"{name}: duplicate ids")
            for e in entries:
                empty = [k for k, v in e.items() if v is None]
                self.assertFalse(empty, f"{name} {e['id']}: keys without values {empty} (quote values that contain commas)")
                self.assertTrue(e.get("summary"), f"{name} {e['id']}: no summary")

    def test_groups_are_defined(self):
        for name, key in CATALOGS.items():
            base = _load(FRAMEWORKS / f"{name}.yaml")
            if "groups" in base:
                for e in base[key]:
                    self.assertIn(e["group"], base["groups"], f"{name} {e['id']}: unknown group {e['group']!r}")

    def test_every_language_covers_every_id(self):
        for lang in i18n.LANGUAGES:
            if lang == i18n.DEFAULT:
                continue
            for name, key in CATALOGS.items():
                self.assertEqual(i18n.missing(FRAMEWORKS, name, lang, key), [], f"{name}: ids without {lang} text")
                over = _load(FRAMEWORKS / lang / f"{name}.yaml")
                base = _load(FRAMEWORKS / f"{name}.yaml")
                extra = set(over["items"]) - {str(e["id"]) for e in base[key]}
                self.assertFalse(extra, f"{name} {lang}: text for ids not in the base catalog: {sorted(extra)}")
                groups = base.get("groups") or {e["group"] for e in base[key]}
                self.assertEqual(set(groups), set(over.get("groups") or {}), f"{name} {lang}: group names differ")

    def test_overlay_changes_only_text(self):
        for name, key in CATALOGS.items():
            base = _load(FRAMEWORKS / f"{name}.yaml")[key]
            de = i18n.load_catalog(FRAMEWORKS, name, "de", key)[key]
            for b, d in zip(base, de):
                for field in set(b) - set(i18n.TEXT_FIELDS) - {"group"}:
                    self.assertEqual(b[field], d[field], f"{name} {b['id']}: overlay changed {field}")


class Crosswalk(unittest.TestCase):
    def test_app_maps_point_at_real_requirements(self):
        """Each app requirement names the GDPR, NIS2, ISO and SOC 2 provisions it supports; every one must exist."""
        ids = {name: {str(e["id"]) for e in _load(FRAMEWORKS / f"{name}.yaml")[key]} for name, key in CATALOGS.items()}
        for e in _load(FRAMEWORKS / "app.yaml")["requirements"]:
            for fw, refs in (e.get("maps") or {}).items():
                self.assertFalse(set(refs) - ids[fw], f"app {e['id']}: unknown {fw} IDs {sorted(set(refs) - ids[fw])}")

    def test_app_finder(self):
        from lib import frameworks

        find = frameworks.finder(FRAMEWORKS, "app")
        self.assertEqual(find("see SEC-AC-01 and DP-SUP-03; not SEC-XX-99"), ["SEC-AC-01", "DP-SUP-03"])


class ReportText(unittest.TestCase):
    def test_languages_have_the_same_keys_and_placeholders(self):
        self.assertTrue(REPORT_TEXTS, "no report text folders found")
        for folder in REPORT_TEXTS:
            en = _load(folder / "en.yaml")
            for lang in i18n.LANGUAGES:
                path = folder / f"{lang}.yaml"
                self.assertTrue(path.exists(), f"missing {path.relative_to(ROOT)}")
                self._same(en, _load(path), f"{path.relative_to(ROOT)}")

    def _same(self, a, b, where):
        self.assertIs(type(a), type(b), where)
        if isinstance(a, dict):
            self.assertEqual(set(a), set(b), f"{where}: keys differ {set(a) ^ set(b)}")
            for k in a:
                self._same(a[k], b[k], f"{where}.{k}")
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b), f"{where}: list length")
            for i, (x, y) in enumerate(zip(a, b)):
                self._same(x, y, f"{where}[{i}]")
        elif isinstance(a, str):
            ph = lambda s: set(re.findall(r"\{\w+\}", s))
            self.assertEqual(ph(a), ph(b), f"{where}: placeholders differ")


class Finders(unittest.TestCase):
    """Connectors turn platform text into catalog IDs with frameworks.finder()."""

    def find(self, name, *texts, annex=None):
        from lib import frameworks

        return frameworks.finder(FRAMEWORKS, name)(*texts, annex=annex)

    def test_soc2(self):
        self.assertEqual(self.find("soc2", "CC6.1 Logical access; see also A1.2"), ["CC6.1", "A1.2"])

    def test_iso27001(self):
        self.assertEqual(self.find("iso27001", "9.2 Internal audit"), ["9.2.1", "9.2.2"])
        self.assertEqual(self.find("iso27001", "A.5.15 Access control"), ["A.5.15"])
        self.assertEqual(self.find("iso27001", "8.24"), ["A.8.24"], "a bare number with no clause is Annex A")

    def test_gdpr(self):
        self.assertEqual(self.find("gdpr", "Art. 30(1) GDPR"), ["Art.30(1)"])
        self.assertEqual(self.find("gdpr", "Article 33 (2)"), ["Art.33(2)"])
        self.assertEqual(self.find("gdpr", "Artikel 33 Abs. 1 DSGVO"), ["Art.33(1)"])
        self.assertIn("Art.32(1)(b)", self.find("gdpr", "Art. 32"), "a whole article expands to its entries")
        self.assertEqual(self.find("gdpr", "Art. 30(1)(g)"), ["Art.30(1)"], "more specific than the catalog falls back to the parent")
        self.assertEqual(self.find("gdpr", "Art. 99"), [])

    def test_nis2(self):
        self.assertEqual(self.find("nis2", "Art. 21(2)(d) supply chain"), ["Art.21(2)(d)"])
        self.assertEqual(self.find("nis2", "IR 6.10 Vulnerability handling"), ["IR.6.10"])
        self.assertEqual(self.find("nis2", "IR.6.1"), ["IR.6.1"], "IR.6.1 is not a prefix match for IR.6.10")


class Privacy(unittest.TestCase):
    def test_regulation_titles_are_not_people(self):
        from lib import privacy

        found = set()
        privacy._harvest_prose("Measures follow the Implementing Regulation (EU) 2024/2690. Approved by Dana Leaver (CEO).", found)
        self.assertEqual(found, {"Dana Leaver"})

    def test_people_registers_are_people(self):
        from lib import privacy

        found = set()
        privacy._walk([{"id": "dana", "name": "Dana Leaver", "email": "dana@example.invalid", "state": "ACTIVE"},
                       {"id": "cloud", "name": "Example Cloud", "category": "CLOUD_PROVIDER"}], found)
        self.assertEqual(found, {"Dana Leaver"})

    def test_structured_names_count_in_any_spelling(self):
        from lib import privacy

        found = set()
        privacy._walk([{"full_name": "José García"}, {"full_name": "Dana van Dijk"}, {"full_name": "Li Wu"}, {"employee": "E-1042"}], found)
        self.assertEqual(found, {"José García", "Dana van Dijk", "Li Wu"})
        self.assertTrue(privacy.leaks("Approved by José García.", found))

    def test_yaml_evidence_is_searched_for_names(self):
        import tempfile
        from lib import privacy

        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / "evidence").mkdir()
            (bundle / "evidence" / "EV-0001_people.yaml").write_text("- full_name: José García\n- full_name: Li Wu\n")
            self.assertEqual(privacy.forbidden(bundle, "context.yaml", set()), {"José García", "Li Wu"})

    def test_csv_exports_are_searched_for_names(self):
        import tempfile
        from lib import privacy

        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / "evidence").mkdir()
            (bundle / "evidence" / "EV-0002_hr.csv").write_text("\ufefffull_name,email\nJosé García,jose@example.invalid\nLi Wu,li@example.invalid\n")
            self.assertEqual(privacy.forbidden(bundle, "context.yaml", set()), {"José García", "Li Wu"})

    def test_probe_never_turns_a_missing_count_into_no_access(self):
        from lib import probes

        self.assertEqual(probes._outcome(200, None), "unknown")
        self.assertEqual(probes._outcome(403, None), "denied to anonymous callers")
        self.assertIn("empty table looks the same", probes._outcome(200, 0))
        self.assertIn("readable by anyone", probes._outcome(206, 42))
        self.assertEqual(probes._bucket_outcome(503, None), "unknown")
        self.assertIn("empty bucket looks the same", probes._bucket_outcome(200, []))
        self.assertEqual(probes._bucket_outcome(403, None), "denied to anonymous callers")

    def test_sharing_a_first_name_with_the_representative_exempts_nobody(self):
        import json, tempfile
        from lib import privacy

        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / "people.json").write_text(json.dumps([{"full_name": "Dana Leaver"}]))
            names = privacy.forbidden(bundle, "system.yaml", {"Dana Manager", "Dana Systems GmbH"})
        self.assertEqual(names, {"Dana Leaver"})

    def test_scan_finds_contact_details_anywhere(self):
        from lib import privacy

        hits = privacy.scan({"cover": {"scope": "Ask ops@example.com"}, "rows": [{"text": "fine"}]}, set())
        self.assertEqual(len(hits), 1)
        self.assertIn("cover.scope", hits[0])

    def test_git_authors_are_people(self):
        from lib import privacy

        found = set()
        privacy._walk([{"commit": "abc", "author": "Sam Joiner", "subject": "Update policy"}], found)
        self.assertEqual(found, {"Sam Joiner"})


class Formatting(unittest.TestCase):
    def test_dates(self):
        d = dt.date(2026, 3, 5)
        self.assertEqual(i18n.fmt_date(d, "en"), "March 5, 2026")
        self.assertEqual(i18n.fmt_date(d, "en", day_first=True), "5 March 2026")
        self.assertEqual(i18n.fmt_date(d, "de"), "5. März 2026")

    def test_join(self):
        self.assertEqual(i18n.join(["a", "b", "c"], "en"), "a, b, and c")
        self.assertEqual(i18n.join(["a", "b", "c"], "de"), "a, b und c")
        self.assertEqual(i18n.join(["a", "b"], "de"), "a und b")

    def test_unknown_language(self):
        with self.assertRaises(i18n.LanguageError):
            i18n.check("fr")


if __name__ == "__main__":
    unittest.main()


class EventWindow(unittest.TestCase):
    def test_point_in_time_keeps_earlier_events(self):
        import datetime as dt
        from types import SimpleNamespace
        from lib.sampling import event_window

        day = dt.date(2026, 6, 30)
        hired, after = dt.date(2026, 2, 1), dt.date(2026, 7, 1)
        for eng in (SimpleNamespace(period=(day, day), point_in_time=True), SimpleNamespace(period=(day, day), report_type=1)):
            keep = event_window(eng)
            self.assertTrue(keep(hired))
            self.assertFalse(keep(after))
        period = event_window(SimpleNamespace(period=(dt.date(2026, 3, 1), day), report_type=2))
        self.assertFalse(period(hired))
        self.assertTrue(period(dt.date(2026, 4, 1)))
