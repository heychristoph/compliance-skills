"""The engagement folder, the framework profile and the requirements catalog.

This is the requirements engine shared by the ISO/IEC 27001, GDPR and NIS2 audit
skills. What differs between them is data: `assets/profile.yaml` (audit types,
applicability, the description file, report highlights), the catalog in
`assets/frameworks/`, and the report wording in `assets/report/text/`.

Every other module goes through `Engagement` to find files, so the folder layout
is defined in exactly one place.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from functools import cached_property
from pathlib import Path

from common import frameworks, i18n
from common.io import (  # file IO shared with every engine and connector
    AuditError, dump_json, dump_yaml, load_json, load_yaml, now_utc, parse_date, read_csv, safe_name, sha256_file, truthy,
    write_csv,
)
from common.io import schema_errors as _schema_errors

ENGINE = Path(__file__).resolve().parent          # scripts/engine/ (copied from shared/engines/requirements)
SKILL_ROOT = ENGINE.parent.parent
ASSETS = SKILL_ROOT / "assets"
SCHEMAS = ENGINE / "schemas"

PROFILE = load_yaml(ASSETS / "profile.yaml")
FRAMEWORK = PROFILE["framework"]
CLI = PROFILE["cli"]
AUDIT_TYPES = {k: v["label"] for k, v in PROFILE["audit_types"].items()}
APPLICABILITY = PROFILE.get("applicability") or {}
DESCRIPTION = {**frameworks.DESCRIPTIONS[FRAMEWORK], **(PROFILE.get("description") or {})}
REQ_PREFIX = "REQ-"  # units for requirements no organization control is mapped to


def schema_errors(data, schema_name: str) -> list[str]:
    """Schema violations against the engine's schemas."""
    return _schema_errors(data, schema_name, SCHEMAS)


# --- the requirements catalog --------------------------------------------------


def load_catalog(lang: str = i18n.DEFAULT) -> dict:
    """The audited framework's catalog, with titles and summaries in `lang`."""
    return frameworks.load(ASSETS / "frameworks", FRAMEWORK, lang)


def load_requirements(lang: str = i18n.DEFAULT) -> list[dict]:
    return load_catalog(lang)["requirements"]


def requirement_index() -> dict[str, dict]:
    return {r["id"]: r for r in load_requirements()}


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
        self.findings_path = self.root / "findings.json"
        self.review = self.root / "review"
        self.qa_path = self.review / "qa.json"
        self.report = self.root / "report"

    # config

    @cached_property
    def config(self) -> dict:
        if not self.config_path.exists():
            raise AuditError(f"No engagement.yaml in {self.root}. Run `{CLI} init {self.root}` first.")
        data = load_yaml(self.config_path)
        errors = schema_errors(data, "engagement")
        atype = data.get("audit_type") if isinstance(data, dict) else None
        if atype is not None and atype not in AUDIT_TYPES:
            errors.append(f"audit_type: '{atype}' is not one of {', '.join(AUDIT_TYPES)}")
        elif atype is not None:
            needed = "as_of" if PROFILE["audit_types"][atype].get("as_of") else "period"
            if needed not in data:
                errors.append(f"(root): a {atype} audit needs '{needed}'")
        scope = APPLICABILITY.get("scope")
        if scope and isinstance(data, dict):
            values = data.get(scope["config"]) or []
            bad = [v for v in values if v not in scope["choices"]]
            if not values:
                errors.append(f"{scope['config']}: set at least one of {', '.join(scope['choices'])} (init --{scope['config'].replace('_', '-')})")
            elif bad:
                errors.append(f"{scope['config']}: {bad} not in {', '.join(scope['choices'])}")
        if errors:
            raise AuditError("engagement.yaml is invalid:\n  " + "\n  ".join(errors))
        return data

    @cached_property
    def framework(self) -> "frameworks.Framework":
        """The audited framework: its catalog, requirement-ID finder and description file."""
        return frameworks.Framework(ASSETS / "frameworks", FRAMEWORK, description=DESCRIPTION, soa=APPLICABILITY.get("soa"))

    @property
    def profile(self) -> dict:
        return PROFILE

    @property
    def language(self) -> str:
        """Language of the report and of the requirement text printed in it (en or de)."""
        try:
            return i18n.check(self.config.get("language"))
        except i18n.LanguageError as e:
            raise AuditError(f"engagement.yaml: {e}") from e

    @property
    def audit_type(self) -> str:
        return self.config["audit_type"]

    @property
    def audit_label(self) -> str:
        return AUDIT_TYPES[self.audit_type]

    @property
    def point_in_time(self) -> bool:
        """Documentation and readiness as of a date (ISO Stage 1, a GDPR or NIS2 assessment);
        every other audit type samples records over a period."""
        return bool(PROFILE["audit_types"][self.audit_type].get("as_of"))

    @property
    def partial(self) -> bool:
        """The audit type may leave units out (ISO surveillance); every other type covers everything in scope."""
        return bool(PROFILE["audit_types"][self.audit_type].get("partial"))

    @property
    def period(self) -> tuple[dt.date, dt.date]:
        """Start and end of the records period; for a point-in-time audit, the single as-of date."""
        if self.point_in_time:
            d = parse_date(self.config["as_of"])
            return d, d
        p = self.config["period"]
        return parse_date(p["start"]), parse_date(p["end"])

    @property
    def period_label(self) -> str:
        """English period label for internal records (review packet, rollup)."""
        start, end = self.period
        if self.point_in_time:
            return f"as of {fmt_date(end)}"
        return f"for records from {fmt_date(start)} to {fmt_date(end)}"

    # requirements in scope

    @cached_property
    def soa(self) -> dict[str, dict] | None:
        """The Statement of Applicability by control, or None if the framework has none or the source had none."""
        if not APPLICABILITY.get("soa"):
            return None
        path = self.bundle / APPLICABILITY["soa"].get("file", "soa.csv")
        if not path.exists():
            return None
        return {r["control"]: r for r in read_csv(path) if r.get("control")}

    @property
    def scope_values(self) -> list[str]:
        """The engagement's scope (GDPR roles, NIS2 entity types), or [] when the framework has none."""
        scope = APPLICABILITY.get("scope")
        return list(self.config.get(scope["config"]) or []) if scope else []

    def applicability(self, req: dict) -> tuple[bool, str]:
        """Whether a requirement is in scope, and why not when it is not.

        - Kinds in `applicability.always` always apply (ISO clauses).
        - With a Statement of Applicability (ISO Annex A), its decision applies. With no
          SoA, every control is treated as applicable; `check` requests the SoA.
        - With a scope attribute (GDPR roles, NIS2 entity types), a requirement applies when
          it names one of the engagement's values.
        - Optional requirements (GDPR codes and certification) apply only when listed in
          `include_optional`.
        The reason is a key into the report text's `labels.excluded` (or the SoA justification).
        """
        if req.get("kind") in (APPLICABILITY.get("always") or []):
            return True, ""
        soa = APPLICABILITY.get("soa")
        if soa and req.get("kind") == soa.get("kind"):
            if self.soa is None:
                return True, ""
            row = self.soa.get(req["id"])
            if row is None or truthy(row.get("applicable", "yes")):
                return True, ""
            return False, "soa"
        scope = APPLICABILITY.get("scope")
        if scope:
            names = req.get(scope["field"]) or []
            if names and not set(names) & set(self.scope_values):
                return False, "scope"
        if req.get(APPLICABILITY.get("optional_field") or "optional") and str(req["id"]) not in (self.config.get("include_optional") or []):
            return False, "optional"
        return True, ""

    def applicable(self, req: dict) -> bool:
        return self.applicability(req)[0]

    @cached_property
    def requirements(self) -> list[dict]:
        """Requirements in scope for this engagement, in report order."""
        return [r for r in load_requirements(self.language) if self.applicable(r)]

    # bundle

    @cached_property
    def manifest(self) -> dict:
        if not self.manifest_path.exists():
            raise AuditError(f"No bundle/manifest.json. Run `{CLI} ingest` first.")
        return load_json(self.manifest_path)

    @cached_property
    def artifacts(self) -> dict[str, dict]:
        return {a["id"]: a for a in self.manifest["artifacts"]}

    def artifact_path(self, artifact_id: str) -> Path:
        return self.bundle / self.artifacts[artifact_id]["path"]

    @cached_property
    def client_controls(self) -> list[dict]:
        """The organization's control matrix, as the connector wrote it."""
        path = self.bundle / "controls.csv"
        if not path.exists():
            raise AuditError("No bundle/controls.csv. The connector must write the control matrix.")
        rows = read_csv(path)
        for row in rows:
            row["criteria"] = row.get("criteria", "").replace(",", " ").replace(";", " ").split()
        return rows

    @cached_property
    def controls(self) -> list[dict]:
        """Every unit of audit work: the organization's controls, plus one REQ- unit for
        each in-scope requirement no control is mapped to.

        Certification audits cover the standard's requirements, not only the
        controls a compliance platform happens to model. A requirement with no
        mapped control is audited directly against its own wording.
        """
        units = list(self.client_controls)
        covered = {x for c in units for x in c["criteria"]}
        title = load_yaml(ASSETS / "report" / "text" / f"{self.language}.yaml")["labels"]["req_unit_title"]
        for req in self.requirements:
            if req["id"] in covered:
                continue
            freq, nature = req.get("plan") or ["continuous", "manual"]
            freq = "event" if freq == "per-event" else freq  # catalog spelling; event-driven units need a population
            units.append({
                "id": f"{REQ_PREFIX}{req['id']}",
                "title": title.format(title=req["title"]),
                "description": req.get("text") or req["summary"],
                "criteria": [req["id"]],
                "owner": "",
                "frequency": freq,
                "nature": nature,
                "population": "",
                "source_ref": "requirements catalog",
            })
        return units

    @property
    def description_path(self) -> Path:
        """The organization's description (isms.yaml, context.yaml): the file at the root overrides the one the connector pulled."""
        root = self.root / DESCRIPTION["file"]
        return root if root.exists() else self.bundle / DESCRIPTION["file"]

    @cached_property
    def description(self) -> dict:
        return load_yaml(self.description_path) if self.description_path.exists() else {}

    def population(self, artifact_id: str) -> list[dict]:
        return read_csv(self.artifact_path(artifact_id))

    # test plan

    def testplan(self) -> list[dict]:
        return read_csv(self.testplan_path) if self.testplan_path.exists() else []

    def included(self) -> set[str]:
        """Control IDs the test plan includes in this audit (all of them unless a surveillance plan leaves some out)."""
        return {r["control_id"] for r in self.testplan() if r.get("include", "yes").lower() != "no"}

    # workpapers

    def qa_binding(self, control_id: str) -> str:
        """The hash a QA review of this workpaper is bound to (the workpaper and every artifact it cites)."""
        from common.io import qa_binding

        return qa_binding(self.workpaper_path(control_id), self.artifacts)

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
        files += [p.relative_to(self.root).as_posix() for p in [self.manifest_path, self.description_path, self.testplan_path, self.findings_path, self.qa_path]]
        files += [p.relative_to(self.root).as_posix() for p in self.workpaper_files()]
        files.append("review/stack.yaml")  # the sub-processor annex is built from it
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
    return i18n.fmt_date(d, lang, day_first=True)
