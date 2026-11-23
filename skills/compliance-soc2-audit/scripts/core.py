"""Shared helpers: the engagement folder layout, file IO, hashing and schema checks.

Every other module goes through `Engagement` to find files, so the folder layout
is defined in exactly one place.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from functools import cached_property
from pathlib import Path

import jsonschema
import yaml

from common import i18n

SKILL_ROOT = Path(__file__).resolve().parent.parent
ASSETS = SKILL_ROOT / "assets"
SCHEMAS = ASSETS / "schemas"

CATEGORY_PREFIX = {
    "security": "CC",
    "availability": "A",
    "confidentiality": "C",
    "processing-integrity": "PI",
    "privacy": "P",
}


from common.io import (  # noqa: E402  (file IO shared with every engine and connector)
    AuditError, dump_json, dump_yaml, load_json, load_yaml, now_utc, parse_date, read_csv, safe_name, sha256_file, truthy,
    write_csv,
)
from common.io import schema_errors as _schema_errors  # noqa: E402
from common import frameworks  # noqa: E402


def schema_errors(data, schema_name: str) -> list[str]:
    """Schema violations against this skill's schemas (assets/schemas/)."""
    return _schema_errors(data, schema_name, SCHEMAS)


def load_criteria(lang: str = i18n.DEFAULT) -> list[dict]:
    """The Trust Services Criteria, with titles and summaries in `lang`."""
    return i18n.load_catalog(ASSETS / "frameworks", "soc2", lang, entries="criteria")["criteria"]


# --- the engagement folder ---------------------------------------------------


class Engagement:
    """One audit engagement on disk. See references/engagement-folder.md for the layout."""

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.config_path = self.root / "engagement.yaml"
        self.bundle = self.root / "bundle"
        self.manifest_path = self.bundle / "manifest.json"
        self.testplan_path = self.root / "testplan.csv"
        self.workpapers = self.root / "workpapers"
        self.opinion_path = self.root / "opinion.json"
        self.review = self.root / "review"
        self.qa_path = self.review / "qa.json"
        self.report = self.root / "report"

    # config

    @cached_property
    def config(self) -> dict:
        if not self.config_path.exists():
            raise AuditError(f"No engagement.yaml in {self.root}. Run `soc2.py init {self.root}` first.")
        data = load_yaml(self.config_path)
        errors = schema_errors(data, "engagement")
        if errors:
            raise AuditError("engagement.yaml is invalid:\n  " + "\n  ".join(errors))
        return data

    @cached_property
    def framework(self) -> "frameworks.Framework":
        """The audited framework: its catalog, requirement-ID finder and description file."""
        return frameworks.Framework(ASSETS / "frameworks", "soc2")

    @property
    def language(self) -> str:
        """Language of the report and of the criteria text printed in it (en or de)."""
        try:
            return i18n.check(self.config.get("language"))
        except i18n.LanguageError as e:
            raise AuditError(f"engagement.yaml: {e}") from e

    @property
    def report_type(self) -> int:
        return self.config["report_type"]

    @property
    def period(self) -> tuple[dt.date, dt.date]:
        """Start and end of the examination; a Type 1 'period' is the single as-of date."""
        if self.report_type == 2:
            p = self.config["period"]
            return parse_date(p["start"]), parse_date(p["end"])
        d = parse_date(self.config["as_of"])
        return d, d

    @property
    def period_label(self) -> str:
        start, end = self.period
        if self.report_type == 1:
            return f"as of {fmt_date(end)}"
        return f"throughout the period {fmt_date(start)} to {fmt_date(end)}"

    @cached_property
    def criteria(self) -> list[dict]:
        """Criteria in scope for this engagement, in report order."""
        cats = set(self.config["categories"])
        return [c for c in load_criteria(self.language) if c["category"] in cats]

    # bundle

    @cached_property
    def manifest(self) -> dict:
        if not self.manifest_path.exists():
            raise AuditError("No bundle/manifest.json. Run `soc2.py ingest` first.")
        return load_json(self.manifest_path)

    @cached_property
    def artifacts(self) -> dict[str, dict]:
        return {a["id"]: a for a in self.manifest["artifacts"]}

    def artifact_path(self, artifact_id: str) -> Path:
        return self.bundle / self.artifacts[artifact_id]["path"]

    @cached_property
    def controls(self) -> list[dict]:
        path = self.bundle / "controls.csv"
        if not path.exists():
            raise AuditError("No bundle/controls.csv. The connector must write the control matrix.")
        rows = read_csv(path)
        for row in rows:
            row["criteria"] = row.get("criteria", "").replace(",", " ").replace(";", " ").split()
        return rows

    @property
    def system_path(self) -> Path:
        """Management's system description: system.yaml at the root overrides the one the connector pulled."""
        root = self.root / "system.yaml"
        return root if root.exists() else self.bundle / "system.yaml"

    @cached_property
    def system(self) -> dict:
        return load_yaml(self.system_path) if self.system_path.exists() else {}

    def population(self, artifact_id: str) -> list[dict]:
        return read_csv(self.artifact_path(artifact_id))

    # workpapers

    def workpaper_path(self, control_id: str) -> Path:
        return self.workpapers / f"{safe_name(control_id)}.json"

    def workpaper_files(self) -> list[Path]:
        return sorted(self.workpapers.glob("*.json")) if self.workpapers.exists() else []

    def load_workpapers(self) -> dict[str, dict]:
        out = {}
        for path in self.workpaper_files():
            wp = load_json(path)
            out[wp.get("control_id", path.stem)] = wp
        return out

    def digest(self) -> str:
        """Hash over everything the report is built from. Sign-off is bound to this value."""
        h = hashlib.sha256()
        files = [self.config_path.name]
        files += [p.relative_to(self.root).as_posix() for p in [self.manifest_path, self.system_path, self.testplan_path, self.opinion_path, self.qa_path]]
        files += [p.relative_to(self.root).as_posix() for p in self.workpaper_files()]
        for rel in files:
            path = self.root / rel
            if not path.exists():
                continue
            if path == self.config_path:
                data = load_yaml(path)
                data.pop("signoff", None)
                content = json.dumps(data, sort_keys=True).encode()
            else:
                content = path.read_bytes()
            h.update(rel.encode() + b"\0" + hashlib.sha256(content).digest())
        return h.hexdigest()




def fmt_date(d: dt.date, lang: str = i18n.DEFAULT) -> str:
    return i18n.fmt_date(d, lang)
