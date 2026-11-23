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
CATALOGS = {"soc2": "criteria", "iso27001": "requirements", "gdpr": "requirements", "nis2": "requirements"}
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
