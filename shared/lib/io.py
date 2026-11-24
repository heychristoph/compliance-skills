"""File IO, hashing, dates and schema checks shared by every audit engine and connector."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

LIB = Path(__file__).resolve().parent
SCHEMAS = LIB / "schemas"  # schemas shared by every engine (the evidence manifest)


class AuditError(Exception):
    """A problem the operator can fix. The message says what is wrong and how to fix it."""


class _StringDateLoader(yaml.SafeLoader):
    """YAML loader that keeps dates as ISO strings, so data round-trips through JSON Schema."""


_StringDateLoader.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_StringDateLoader)


def dump_yaml(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=100)


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(f)]


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def qa_binding(workpaper: Path, artifacts: dict) -> str:
    """What a QA review is bound to: the workpaper's bytes and the content hash of every artifact it cites
    (evidence lists anywhere in it, and the population it was sampled from). If a cited artifact keeps its ID
    but its content changes on a new ingest, the review no longer holds."""
    raw = workpaper.read_bytes()
    cited: set[str] = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "evidence" and isinstance(v, list):
                    cited.update(i for i in v if isinstance(i, str))
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    wp = json.loads(raw)
    walk(wp)
    pop = (wp.get("plan") or {}).get("population") or {}
    if pop.get("source"):
        cited.add(pop["source"])
    h = hashlib.sha256(raw)
    for i in sorted(cited):
        h.update(f"\0{i}\0{(artifacts.get(i) or {}).get('sha256', '')}".encode())
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def schema_errors(data, schema_name: str, schemas_dir: Path = SCHEMAS) -> list[str]:
    """Return human-readable schema violations, each with the JSON path that failed."""
    import jsonschema

    schema = load_json(schemas_dir / f"{schema_name}.schema.json")
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{where}: {err.message}")
    return errors


def bundle_integrity(bundle: Path, manifest: dict) -> list[str]:
    """Every registered evidence file is present and unchanged since ingest.

    Run at every gate a report passes (final validation, sign-off, render), not only at `check`:
    a conclusion must never outlive the evidence it cites."""
    errors = []
    for a in manifest.get("artifacts") or []:
        path = bundle / a["path"]
        if not path.exists():
            errors.append(f"{a['id']}: evidence file {a['path']} is missing from the bundle; restore it or re-ingest and re-test")
        elif sha256_file(path) != a["sha256"]:
            errors.append(f"{a['id']}: evidence file {a['path']} changed after ingest (hash mismatch); re-ingest and re-test the units citing it")
    return errors


def tool_version() -> str:
    """Version of the shared code and catalogs (shared/lib/VERSION), stamped on engagements."""
    path = LIB / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "unknown"


def safe_name(control_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in control_id)


def truthy(value) -> bool:
    return str(value).strip().lower() in ("yes", "y", "true", "1", "applicable", "included")


# --- HTTP ---------------------------------------------------------------------

CREDENTIAL_HEADERS = {"authorization", "cookie", "apikey", "x-api-key", "proxy-authorization"}


def same_origin(a: str, b: str) -> bool:
    """Same scheme, host and effective port. A URL that merely starts with the base (`https://us.probo.com.evil`)
    or uses another port is a different origin, and never gets the base's credentials."""
    pa, pb = urllib.parse.urlsplit(a), urllib.parse.urlsplit(b)
    default = {"https": 443, "http": 80}
    try:
        ports = (pa.port or default.get(pa.scheme.lower()), pb.port or default.get(pb.scheme.lower()))
    except ValueError:
        return False
    return (pa.scheme.lower(), (pa.hostname or "").lower(), ports[0]) == (pb.scheme.lower(), (pb.hostname or "").lower(), ports[1]) \
        and bool(pa.hostname)


class _CredentialSafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but never carry credentials to another origin (urllib forwards them by default)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not same_origin(req.full_url, newurl):
            for store in (new.headers, new.unredirected_hdrs):
                for k in [k for k in store if k.lower() in CREDENTIAL_HEADERS]:
                    del store[k]
        return new


OPENER = urllib.request.build_opener(_CredentialSafeRedirect())


def urlopen(req, timeout: int):
    """urllib.request.urlopen, with credentials dropped on cross-origin redirects."""
    return OPENER.open(req, timeout=timeout)
