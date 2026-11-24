# Copied from shared/lib/codescan.py by tools/sync.py. Edit that file, not this copy.
"""A deterministic scan of an application's repository: what a reviewer checks first.

It reads files only, runs nothing, and never prints a secret: matches are shown with
their middle replaced. The result is evidence (tier `direct`: a script read it from
the code itself) and feeds stack detection:

- secrets in code, especially in code that ships to the browser (a Supabase
  service-role key, payment or AI API keys, private keys)
- committed environment files
- authorization decided in the browser (role checks in client code)
- third-party services the code sends data to: AI APIs, analytics, error tracking,
  email, payments. Each is a sub-processor candidate.
- the database tables the client reads and writes directly (for row-level security checks)
- dependencies and whether a lockfile pins them
"""

from __future__ import annotations

import base64
import json
import re
import unicodedata
from pathlib import Path

from .capture import git_read

SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".vercel", ".output", "coverage", ".venv", "venv", "__pycache__", ".turbo"}
TEXT_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".html", ".json", ".toml", ".yaml", ".yml",
            ".env", ".py", ".sql", ".md", ".txt", ".astro"}
# Code that runs on a server, not in the browser. Everything else in a web app is treated as client code.
SERVER_HINTS = ("supabase/functions/", "supabase/migrations/", "functions/", "api/", "server/", "backend/", "scripts/", "migrations/",
                "netlify/functions/", "app/api/", "pages/api/")
MAX_BYTES = 1_000_000

SECRETS = [
    ("stripe-live-key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{16,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
]
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
SERVICE_ROLE_NAME = re.compile(r"SERVICE_ROLE|service_role", re.I)
CLIENT_ROLE_CHECK = re.compile(r"""\b(?:role|isAdmin|is_admin|user\.role|profile\.role)\s*(?:===?|!==?)\s*['"]?(?:admin|owner|superuser|staff)""", re.I)
AI_IMPORT = re.compile(r"""(?:from\s+|require\(\s*|import\(\s*)['"](openai|@anthropic-ai/sdk|@google/generative-ai|@google/genai|@mistralai/mistralai|groq-sdk|replicate)['"]""")
SUPABASE_URL = re.compile(r"https://[a-z0-9]{12,40}\.supabase\.(?:co|in)")
SUPABASE_TABLE = re.compile(r"""\.from\(\s*['"]([A-Za-z0-9_.]+)['"]\s*\)""")
SUPABASE_BUCKET = re.compile(r"""\.storage\s*\.from\(\s*['"]([A-Za-z0-9_.-]+)['"]\s*\)""")

# Package or host -> (service, category). A sub-processor candidate whenever the code uses it.
SERVICES = {
    "openai": ("OpenAI", "ai"), "@anthropic-ai/sdk": ("Anthropic", "ai"), "@google/generative-ai": ("Google Gemini", "ai"),
    "@google/genai": ("Google Gemini", "ai"), "@mistralai/mistralai": ("Mistral AI", "ai"), "groq-sdk": ("Groq", "ai"),
    "replicate": ("Replicate", "ai"), "@ai-sdk/openai": ("OpenAI", "ai"), "@ai-sdk/anthropic": ("Anthropic", "ai"),
    "@supabase/supabase-js": ("Supabase", "backend"), "@supabase/ssr": ("Supabase", "backend"), "firebase": ("Google Firebase", "backend"),
    "posthog-js": ("PostHog", "analytics"), "mixpanel-browser": ("Mixpanel", "analytics"), "@segment/analytics-next": ("Segment", "analytics"),
    "@vercel/analytics": ("Vercel Analytics", "analytics"), "react-ga4": ("Google Analytics", "analytics"),
    "@sentry/react": ("Sentry", "error tracking"), "@sentry/browser": ("Sentry", "error tracking"), "@sentry/nextjs": ("Sentry", "error tracking"),
    "resend": ("Resend", "email"), "@sendgrid/mail": ("Twilio SendGrid", "email"), "postmark": ("Postmark", "email"),
    "stripe": ("Stripe", "payments"), "@stripe/stripe-js": ("Stripe", "payments"),
    "@clerk/clerk-react": ("Clerk", "authentication"), "@auth0/auth0-react": ("Auth0", "authentication"),
    "@upstash/redis": ("Upstash", "database"), "@vercel/blob": ("Vercel Blob", "storage"), "uploadthing": ("UploadThing", "storage"),
}
HOSTS = {
    "api.openai.com": ("OpenAI", "ai"), "api.anthropic.com": ("Anthropic", "ai"), "generativelanguage.googleapis.com": ("Google Gemini", "ai"),
    "googletagmanager.com": ("Google Analytics", "analytics"), "plausible.io": ("Plausible", "analytics"), "api.resend.com": ("Resend", "email"),
}


def scan(repo: Path) -> dict:
    """Scan a repository checkout. Returns {findings, services, tables, buckets, dependencies, lockfile, files_scanned}."""
    repo = Path(repo)
    if not repo.is_dir():
        raise FileNotFoundError(f"{repo} is not a directory")
    findings: list[dict] = []
    services: dict[str, dict] = {}
    tables: set[str] = set()
    buckets: set[str] = set()
    supabase = {"url": None, "anon_key_in": None}
    tracked = _git_tracked(repo)
    # Compare in one Unicode form: macOS file names are decomposed, git reports them composed.
    tracked = {unicodedata.normalize("NFC", t) for t in tracked} if tracked is not None else None
    files = [p for p in _files(repo) if tracked is None or unicodedata.normalize("NFC", p.relative_to(repo).as_posix()) in tracked]
    for path in files:
        rel = path.relative_to(repo).as_posix()
        if _is_env_file(path):
            findings.append({"rule": "env-file-committed", "severity": "high", "file": rel, "line": 0,
                             "detail": "an environment file is committed to the repository"})
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        client = _is_client(rel)
        for n, line in enumerate(text.splitlines(), 1):
            for rule, rx in SECRETS:
                for m in rx.finditer(line):
                    findings.append({"rule": rule, "severity": "high" if client else "medium", "file": rel, "line": n,
                                     "detail": f"{_mask(m.group(0))} in {'client' if client else 'server or config'} code"})
            if not supabase["url"]:
                m = SUPABASE_URL.search(line)
                supabase["url"] = m.group(0) if m else None
            for m in JWT.finditer(line):
                role = _jwt_role(m.group(0))
                if role == "anon" and not supabase["anon_key_in"]:
                    supabase["anon_key_in"] = f"{rel}:{n}"
                if role == "service_role":
                    findings.append({"rule": "supabase-service-role-key", "severity": "critical" if client else "high", "file": rel, "line": n,
                                     "detail": f"a Supabase service-role key ({_mask(m.group(0))}) in {'client' if client else 'repository'} code: "
                                               "it bypasses row-level security"})
            if client and SERVICE_ROLE_NAME.search(line) and not rel.endswith((".md", ".toml", ".sql")):
                findings.append({"rule": "service-role-in-client", "severity": "high", "file": rel, "line": n,
                                 "detail": "client code refers to a service-role key"})
            if client and CLIENT_ROLE_CHECK.search(line):
                findings.append({"rule": "client-side-authorization", "severity": "medium", "file": rel, "line": n,
                                 "detail": "a role check in browser code; the server or database must enforce it too"})
            if client and AI_IMPORT.search(line):
                findings.append({"rule": "ai-sdk-in-client", "severity": "high", "file": rel, "line": n,
                                 "detail": "an AI SDK is used in browser code: the API key and the prompts are exposed to every user"})
            for m in SUPABASE_BUCKET.finditer(line):
                buckets.add(m.group(1))
            for m in SUPABASE_TABLE.finditer(SUPABASE_BUCKET.sub("", line)):
                tables.add(m.group(1))
            for host, (name, cat) in HOSTS.items():
                if host in line:
                    services.setdefault(name, {"name": name, "category": cat, "evidence": []})["evidence"].append(f"{rel}:{n}")
    deps, lockfile = _dependencies(repo)
    for dep in deps:
        if dep in SERVICES:
            name, cat = SERVICES[dep]
            services.setdefault(name, {"name": name, "category": cat, "evidence": []})["evidence"].append(f"package.json: {dep}")
    for s in services.values():
        s["evidence"] = s["evidence"][:5]
    return {
        "findings": findings,
        "services": sorted(services.values(), key=lambda s: (s["category"], s["name"])),
        "tables": sorted(tables),
        "buckets": sorted(buckets),
        "dependencies": deps,
        "lockfile": lockfile,
        "supabase": supabase,
        "files_scanned": len(files),
        "git_tracked_only": tracked is not None,
    }


def _files(repo: Path):
    for path in repo.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(repo).parts):
            continue
        if path.is_file() and (path.suffix in TEXT_EXT or path.name.startswith(".env")) and path.stat().st_size <= MAX_BYTES:
            yield path


def _git_tracked(repo: Path) -> set[str] | None:
    """Files git tracks, so build output and local-only files are not scanned. None outside git."""
    out = git_read(repo, "ls-files", "-z")  # NUL-separated: no quoting of non-ASCII or special file names
    return {p for p in out.split("\0") if p} if out is not None else None


def _is_env_file(path: Path) -> bool:
    name = path.name
    return name.startswith(".env") and not any(name.endswith(x) for x in (".example", ".sample", ".template", ".dist"))


def _is_client(rel: str) -> bool:
    if any(rel.startswith(h) or f"/{h}" in rel for h in SERVER_HINTS):
        return False
    return rel.endswith((".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html", ".astro", ".mjs")) or rel.startswith(".env")


def _jwt_role(token: str) -> str | None:
    try:
        body = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return data.get("role")
    except (ValueError, IndexError, json.JSONDecodeError):
        return None


def _mask(secret: str) -> str:
    return secret[:6] + "…" + secret[-4:] if len(secret) > 14 else "…"


def _dependencies(repo: Path) -> tuple[list[str], str | None]:
    deps: list[str] = []
    for pkg in sorted(repo.glob("**/package.json")):
        if any(part in SKIP_DIRS for part in pkg.relative_to(repo).parts):
            continue
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("dependencies", "devDependencies"):
            deps += [d for d in (data.get(key) or {}) if d not in deps]
    lock = next((n for n in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock") if (repo / n).exists()), None)
    return sorted(deps), lock


def supabase_anon_key(repo: Path) -> tuple[str | None, str | None]:
    """The Supabase URL and public anon key the app ships to browsers (for probes.supabase_anon). Never logged."""
    repo = Path(repo)
    url = key = None
    for path in _files(repo):
        if not _is_client(path.relative_to(repo).as_posix()):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        url = url or (m.group(0) if (m := SUPABASE_URL.search(text)) else None)
        for m in JWT.finditer(text):
            if _jwt_role(m.group(0)) == "anon":
                key = key or m.group(0)
        if url and key:
            break
    return url, key
