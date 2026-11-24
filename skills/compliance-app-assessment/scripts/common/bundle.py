# Copied from shared/lib/bundle.py by tools/sync.py. Edit that file, not this copy.
"""BundleWriter: the only way connectors write to bundle/.

It owns file layout, artifact IDs, hashing and the manifest, so every connector
produces the same shape and the audit steps never need to know the source. Shared
by every audit skill; the framework-specific parts (which requirement IDs exist,
which description file the engine reads) come from the engagement's `Framework`.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from .io import AuditError, dump_json, dump_yaml, now_utc, parse_date, schema_errors, sha256_file, write_csv, urlopen

CONTROL_COLUMNS = ["id", "title", "description", "criteria", "owner", "frequency", "nature", "population", "source_ref"]
SOA_COLUMNS = ["control", "applicable", "justification", "status", "reference"]

def safe_filename(name: str, fallback: str = "file") -> str:
    """A file name a source supplied, reduced to a plain basename: no directories, no traversal,
    no control characters. Evidence from Vanta, Probo or a folder can never write outside the bundle."""
    base = re.sub(r"[\x00-\x1f\x7f]", "", str(name or "")).replace("\\", "/").split("/")[-1].strip()
    base = base.lstrip(".") or fallback
    return base[:150]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "item"


class BundleWriter:
    def __init__(self, bundle_dir: Path, connector: str, source: str = "", framework=None):
        self.dir = bundle_dir
        self.connector = connector
        self.source = source
        # The audited framework (frameworks.Framework): its catalog name, its ID finder
        # and the description file its engine reads. None only in tests of the writer.
        self.framework = framework
        self.artifacts: list[dict] = []
        self.warnings: list[str] = []
        self._next_ev = 1
        # Re-ingest: an artifact whose source and content are unchanged keeps its ID, so workpapers
        # keep citing it. Changed or new artifacts get IDs never used before in this engagement.
        self._previous: dict[tuple[str, str, str], str] = {}
        self._reserved: set[str] = set()
        self._used: set[str] = set()
        self.dir.mkdir(parents=True, exist_ok=True)

    def keep_ids_from(self, manifest: dict) -> None:
        """Reuse the artifact IDs of a previous ingest for unchanged artifacts."""
        for a in manifest.get("artifacts") or []:
            if a["id"].startswith("EV-"):
                self._previous[(a.get("source_ref") or "", a["title"], a["sha256"])] = a["id"]
                self._reserved.add(a["id"])
        # Every ID any earlier ingest used, so an ID retired two ingests ago is not handed out again
        # and an old citation cannot silently point at different evidence.
        self._reserved |= set(manifest.get("id_history") or [])

    # --- helpers for connectors ---

    def warn(self, message: str) -> None:
        """Record something the auditor should know about the pull (missing data, API errors)."""
        print(f"warning: {message}")
        self.warnings.append(message)

    @staticmethod
    def http_json(url: str, *, method: str = "GET", headers: dict | None = None, body=None, timeout: int = 60):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Accept": "application/json", **(headers or {})})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None, dict(resp.headers)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise AuditError(f"{method} {url} failed with HTTP {e.code}: {detail}") from e

    @staticmethod
    def http_download(url: str, dest: Path, *, headers: dict | None = None, timeout: int = 120) -> None:
        req = urllib.request.Request(url, headers=headers or {})
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
        except urllib.error.HTTPError as e:
            raise AuditError(f"Download of {url} failed with HTTP {e.code}") from e
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            raise AuditError(f"Download of {url} failed: {e}") from e

    # --- writing the bundle ---

    def set_controls(self, rows: list[dict]) -> None:
        """Write the control matrix. `criteria` may be a list or a space-separated string of requirement IDs."""
        if any(x["id"] == "SY-controls" for x in self.artifacts):
            raise AuditError(f"Two sources both provide the control matrix ({self.connector}); keep one control source and "
                             "add the others as evidence-only sources (intake, folder without controls.csv).")
        clean = []
        for row in rows:
            row = dict(row)
            if isinstance(row.get("criteria"), (list, tuple)):
                row["criteria"] = " ".join(row["criteria"])
            clean.append(row)
        path = self.dir / "controls.csv"
        write_csv(path, clean, CONTROL_COLUMNS)
        self._register(path, "SY-controls", kind="controls", title="Control matrix", obtained="client")

    def set_soa(self, rows: list[dict], *, obtained: str = "client", source_ref: str = "") -> None:
        """Write the Statement of Applicability: one row per Annex A control (control, applicable, justification, status, reference)."""
        clean = []
        for row in rows:
            row = dict(row)
            if isinstance(row.get("applicable"), bool):
                row["applicable"] = "yes" if row["applicable"] else "no"
            clean.append(row)
        path = self.dir / "soa.csv"
        write_csv(path, clean, SOA_COLUMNS)
        self._register(path, "SY-soa", kind="soa", title="Statement of Applicability", obtained=obtained, source_ref=source_ref,
                       requirements=["6.1.3"], media_type="text/csv")

    def find(self, *texts, annex: bool | None = None) -> list[str]:
        """Requirement IDs of the audited framework mentioned in free text."""
        return self.framework.find(*texts, annex=annex) if self.framework else []

    def set_description(self, data: dict, *, obtained: str = "client") -> None:
        """Write the framework's description inputs: system.yaml (SOC 2), isms.yaml (ISO 27001) or context.yaml.

        Which file, its title and the requirements it supports come from the framework,
        so a connector writes one dict and every engine finds it where it looks.
        """
        d = self.framework.description
        path = self.dir / d["file"]
        dump_yaml(data, path)
        self._register(path, f"SY-{d['kind']}", kind=d["kind"], title=d["title"], obtained=obtained,
                       requirements=d.get("requirements") or [])

    def set_system(self, system: dict, *, obtained: str = "client") -> None:
        """Write management's system description inputs for a SOC 2 engagement."""
        path = self.dir / "system.yaml"
        dump_yaml(system, path)
        self._register(path, "SY-system", kind="system", title="System description inputs", obtained=obtained)

    def set_isms(self, isms: dict, *, obtained: str = "client") -> None:
        """Write the ISMS scope and context inputs for an ISO/IEC 27001 engagement."""
        path = self.dir / "isms.yaml"
        dump_yaml(isms, path)
        self._register(path, "SY-isms", kind="isms", title="ISMS scope and context inputs", obtained=obtained,
                       requirements=["4.1", "4.2", "4.3"])

    def add_population(self, name: str, rows: list[dict], *, title: str, obtained: str = "direct", source_ref: str = "") -> str:
        """Write a population file. Each row needs `id` and `date`; other columns are kept."""
        seen: set[str] = set()
        for i, row in enumerate(rows):
            if not row.get("id") or not row.get("date"):
                raise AuditError(f"Population '{name}' row {i + 1} needs non-empty 'id' and 'date' columns.")
            if parse_date(row["date"]) is None:
                raise AuditError(f"Population '{name}' row {i + 1} ({row['id']}) has an invalid date {row['date']!r}; "
                                 "use YYYY-MM-DD so the event is neither lost nor misplaced in the period.")
            if str(row["id"]) in seen:
                raise AuditError(f"Population '{name}' row {i + 1} repeats item ID {row['id']}; each event must appear once.")
            seen.add(str(row["id"]))
        artifact_id = f"PO-{slug(name)}"
        path = self.dir / "populations" / f"{slug(name)}.csv"
        extra = []
        for row in rows:
            extra += [k for k in row if k not in ("id", "date") and k not in extra]
        write_csv(path, rows, ["id", "date", *extra])
        self._register(path, artifact_id, kind="population", title=title, obtained=obtained, source_ref=source_ref, media_type="text/csv")
        return artifact_id

    def add_file(self, src: Path, *, title: str, kind: str = "evidence", controls=(), requirements=(), date: str | None = None,
                 obtained: str = "direct", source_ref: str = "", filename: str | None = None, capture: dict | None = None) -> str:
        """Copy a file into bundle/evidence/ and register it. Returns the artifact ID."""
        artifact_id = self._new_id(source_ref, title, sha256_file(Path(src)) if self._previous else None)
        dest = self._evidence_path(artifact_id, filename or Path(src).name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        self._register(dest, artifact_id, kind=kind, title=title, controls=controls, requirements=requirements, date=date,
                       obtained=obtained, source_ref=source_ref, capture=capture)
        return artifact_id

    def add_bytes(self, content: bytes | str, filename: str, *, title: str, kind: str = "evidence", controls=(), requirements=(),
                  date: str | None = None, obtained: str = "direct", source_ref: str = "") -> str:
        data = content.encode() if isinstance(content, str) else content
        artifact_id = self._new_id(source_ref, title, hashlib.sha256(data).hexdigest() if self._previous else None)
        dest = self._evidence_path(artifact_id, filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        self._register(dest, artifact_id, kind=kind, title=title, controls=controls, requirements=requirements, date=date,
                       obtained=obtained, source_ref=source_ref)
        return artifact_id

    def _evidence_path(self, artifact_id: str, filename: str) -> Path:
        evidence = (self.dir / "evidence").resolve()
        dest = evidence / f"{artifact_id}_{safe_filename(filename)}"
        if dest.resolve().parent != evidence:
            raise AuditError(f"evidence file name {filename!r} would leave the bundle")
        return self.dir / "evidence" / dest.name

    def add_download(self, url: str, filename: str, *, title: str, headers: dict | None = None, **meta) -> str | None:
        """Download a file into the bundle. On failure, records a warning and returns None."""
        if self._previous:
            tmp = self.dir / "evidence" / f".download-{len(self.artifacts)}"
            try:
                self.http_download(url, tmp, headers=headers)
            except AuditError as e:
                self.warn(f"could not download '{title}': {e}")
                return None
            artifact_id = self._new_id(meta.get("source_ref") or "", title, sha256_file(tmp))
            dest = self._evidence_path(artifact_id, filename)
            tmp.rename(dest)
            self._register(dest, artifact_id, title=title, **{"kind": "evidence", **meta})
            return artifact_id
        artifact_id = self._new_id()
        dest = self._evidence_path(artifact_id, filename)
        try:
            self.http_download(url, dest, headers=headers)
        except AuditError as e:
            self.warn(f"could not download '{title}': {e}")
            return None
        self._register(dest, artifact_id, title=title, **{"kind": "evidence", **meta})
        return artifact_id

    def finish(self) -> dict:
        manifest = {
            "schema_version": 1,
            "connector": self.connector,
            "source": self.source,
            "collected_at": now_utc(),
            "warnings": self.warnings,
            "artifacts": self.artifacts,
            "id_history": sorted(self._reserved | {x for x in self._used if x.startswith("EV-")}),
        }
        errors = schema_errors(manifest, "manifest")
        if errors:
            raise AuditError("Connector produced an invalid manifest:\n  " + "\n  ".join(errors[:20]))
        dump_json(manifest, self.dir / "manifest.json")
        return manifest

    # --- internals ---

    def _new_id(self, source_ref: str = "", title: str = "", sha: str | None = None) -> str:
        if sha is not None:
            prev = self._previous.get((source_ref or "", title, sha))
            if prev and prev not in self._used:
                self._used.add(prev)
                return prev
        while True:
            artifact_id = f"EV-{self._next_ev:04d}"
            self._next_ev += 1
            if artifact_id not in self._reserved and artifact_id not in self._used:
                self._used.add(artifact_id)
                return artifact_id

    def _register(self, path: Path, artifact_id: str, *, kind: str, title: str, controls=(), requirements=(), date=None,
                  obtained: str = "direct", source_ref: str = "", media_type: str | None = None, capture: dict | None = None) -> None:
        if any(a["id"] == artifact_id for a in self.artifacts):
            raise AuditError(f"Duplicate artifact ID {artifact_id}; population names must be unique.")
        root = self.dir.resolve()
        if root not in path.resolve().parents:
            raise AuditError(f"{path} is outside the bundle")
        entry = {
            "id": artifact_id,
            "path": path.relative_to(self.dir).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "kind": kind,
            "title": title,
            "media_type": media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "controls": sorted(set(controls)),
            "obtained": obtained,
        }
        if requirements:
            entry["requirements"] = list(dict.fromkeys(requirements))
        if capture:
            entry["capture"] = capture
        if date:
            entry["date"] = str(date)[:10]
        if source_ref:
            entry["source_ref"] = source_ref
        self.artifacts.append(entry)
