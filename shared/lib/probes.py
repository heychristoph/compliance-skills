"""Active checks that prove what an anonymous visitor can reach. Read-only, and they read no data.

`supabase-anon` uses the project's public anon key, the one every visitor's browser already
has, to ask the live API, for every table and storage bucket:
  - tables: a HEAD request with `Prefer: count=exact` returns only how many rows an anonymous
    caller would see (Content-Range), never the rows. More than 0 on a table with personal
    data means row-level security does not protect it from the public.
  - buckets: listing one object (limit 1) shows whether anyone can enumerate the files; only
    the yes/no is kept, not the file name.
It never uses a service-role key, never writes, and sends one request per table and bucket.
Run it only on a project the user is authorized to test (`probe --authorized`).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from .io import AuditError, now_utc

TIMEOUT = 20


def supabase_anon(url: str, key: str, tables: list[str], buckets: list[str]) -> dict:
    base = url.rstrip("/")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    exposed, openapi_status = _openapi_tables(base, headers)
    names = sorted(set(tables) | set(exposed))
    out_tables = []
    for t in names:
        status, rng = _request("HEAD", f"{base}/rest/v1/{quote(t)}?select=*",
                               {**headers, "Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"})
        count = _count(rng)
        out_tables.append({"table": t, "status": status, "visible_rows": count,
                           "exposed_in_api": t in exposed,
                           "result": "readable by anyone" if count else ("not readable anonymously" if status in (200, 206, 401, 403, 404) else "unknown")})
    out_buckets = []
    for b in sorted(set(buckets)):
        status, body = _request("POST", f"{base}/storage/v1/object/list/{quote(b)}", {**headers, "Content-Type": "application/json"},
                                json.dumps({"prefix": "", "limit": 1, "offset": 0}).encode(), want_body=True)
        listable = status == 200 and isinstance(body, list) and len(body) > 0
        out_buckets.append({"bucket": b, "status": status, "listable_by_anyone": listable})
    return {"probe": "supabase-anon", "project": urlparse(base).netloc, "at": now_utc(), "api_schema_status": openapi_status,
            "tables": out_tables, "buckets": out_buckets,
            "summary": {"tables_readable_by_anyone": [t["table"] for t in out_tables if t["visible_rows"]],
                        "buckets_listable_by_anyone": [b["bucket"] for b in out_buckets if b["listable_by_anyone"]]}}


def _openapi_tables(base: str, headers: dict) -> tuple[list[str], int]:
    status, body = _request("GET", f"{base}/rest/v1/", {**headers, "Accept": "application/openapi+json"}, want_body=True)
    paths = (body or {}).get("paths") or {} if isinstance(body, dict) else {}
    return sorted(p.strip("/") for p in paths if p.strip("/") and not p.startswith("/rpc/")), status


def _count(content_range: str | None) -> int:
    m = re.search(r"/(\d+)$", content_range or "")
    return int(m.group(1)) if m else 0


def _request(method: str, url: str, headers: dict, data: bytes | None = None, want_body: bool = False):
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if want_body:
                raw = resp.read()
                try:
                    return resp.status, json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    return resp.status, None
            return resp.status, resp.headers.get("Content-Range")
    except urllib.error.HTTPError as e:
        return e.code, (None if want_body else e.headers.get("Content-Range"))
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise AuditError(f"{method} {urlparse(url).netloc}: {e}") from e


PROBES = {"supabase-anon": supabase_anon}
