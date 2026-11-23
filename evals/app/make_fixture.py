#!/usr/bin/env python3
"""Build the synthetic app-assessment fixtures: a small Lovable-built Supabase app with planted weaknesses.

    python evals/app/make_fixture.py

Writes evals/app/fixtures/<case>/ for the cases `processor` (the supplier runs production)
and `developer` (the client runs it). Each case has:

  app/                 the application's repository (a git checkout), scanned by `detect`
  engagement.yaml      sources: intake (no compliance platform, no control matrix)
  context.yaml         the description printed in Section II (en; context.de.yaml for German runs)
  captures/            recorded results of MCP calls, exports and answers, replayed through `capture`
  captures.yaml        how to replay each capture (route, title, requirements, tool or question)
  truth.json           the planted defects, the answers-only requirements, and what detect must find

Nothing here calls a model or a network service: the MCP responses were written by hand
in the shape the Supabase MCP server returns.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures"
AS_OF = "2026-11-20"

# A JWT whose payload says role=service_role (signature is not real). codescan decodes the role.
SERVICE_ROLE_JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV4YW1wbGVyZWYiLCJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNzAwMDAwMDAwfQ."
                    "c2lnbmF0dXJlLW5vdC1yZWFsLWZpeHR1cmUtb25seQ")
ANON_JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV4YW1wbGVyZWYiLCJyb2xlIjoiYW5vbiIsImlhdCI6MTcwMDAwMDAwMH0."
            "c2lnbmF0dXJlLW5vdC1yZWFsLWZpeHR1cmUtb25seQ")

APP_FILES = {
    "package.json": json.dumps({
        "name": "kestrel-bookings", "private": True, "version": "0.1.0", "type": "module",
        "dependencies": {"@supabase/supabase-js": "^2.45.0", "openai": "^4.60.0", "react": "^18.3.1", "react-dom": "^18.3.1", "react-router-dom": "^6.26.0"},
        "devDependencies": {"lovable-tagger": "^1.1.0", "vite": "^5.4.0", "typescript": "^5.5.0"},
    }, indent=2),
    "package-lock.json": "{}\n",
    "README.md": "# Kestrel Bookings\n\nBuilt with [Lovable](https://lovable.dev). Booking and client records for a physiotherapy practice group.\n",
    "index.html": "<!doctype html><html><head><title>Kestrel Bookings</title></head><body><div id=\"root\"></div></body></html>\n",
    "src/lib/supabase.ts": (
        "import { createClient } from '@supabase/supabase-js'\n\n"
        "const url = 'https://examplerefxyz.supabase.co'\n"
        f"export const supabase = createClient(url, '{ANON_JWT}')\n\n"
        "// TODO remove: used by the admin page to list all bookings\n"
        f"export const admin = createClient(url, '{SERVICE_ROLE_JWT}')\n"),
    "src/lib/ai.ts": (
        "import OpenAI from 'openai'\n\n"
        "const client = new OpenAI({ apiKey: import.meta.env.VITE_OPENAI_KEY, dangerouslyAllowBrowser: true })\n\n"
        "export async function summarizeNotes(notes: string) {\n"
        "  const r = await client.chat.completions.create({ model: 'gpt-4o-mini', messages: [{ role: 'user', content: notes }] })\n"
        "  return r.choices[0].message.content\n}\n"),
    "src/pages/Admin.tsx": (
        "import { admin } from '../lib/supabase'\n\n"
        "export default function Admin({ profile }: { profile: { role: string } }) {\n"
        "  if (profile.role !== 'admin') return null\n"
        "  // lists every booking of every patient\n"
        "  return <BookingList source={admin.from('bookings')} />\n}\n"),
    "src/pages/Notes.tsx": (
        "import { supabase } from '../lib/supabase'\n\n"
        "export async function loadNotes() { return supabase.from('treatment_notes').select('*') }\n"
        "export async function uploadId(file: File) { return supabase.storage.from('id-documents').upload(file.name, file) }\n"),
    "supabase/migrations/20260301_init.sql": (
        "create table public.bookings (id uuid primary key, patient_id uuid, starts_at timestamptz);\n"
        "alter table public.bookings enable row level security;\n"
        "create policy own_bookings on public.bookings for select using (patient_id = auth.uid());\n"
        "create table public.treatment_notes (id uuid primary key, patient_id uuid, body text);\n"),
    ".env.example": "VITE_SUPABASE_URL=\nVITE_OPENAI_KEY=\n",
}

ADVISORS = [
    {"name": "rls_disabled_in_public", "title": "RLS Disabled in Public", "level": "ERROR", "facing": "EXTERNAL",
     "categories": ["SECURITY"], "detail": "Table `public.treatment_notes` is public, but RLS has not been enabled.",
     "metadata": {"schema": "public", "name": "treatment_notes", "type": "table"}},
    {"name": "auth_leaked_password_protection", "title": "Leaked Password Protection Disabled", "level": "WARN", "facing": "EXTERNAL",
     "categories": ["SECURITY"], "detail": "Leaked password protection is currently disabled.", "metadata": {}},
]
RLS = [
    {"schema": "public", "table": "bookings", "rls_enabled": True, "rls_forced": False,
     "policies": [{"policy": "own_bookings", "cmd": "SELECT", "roles": ["public"], "using": "(patient_id = auth.uid())", "check": None}]},
    {"schema": "public", "table": "treatment_notes", "rls_enabled": False, "rls_forced": False, "policies": None},
]
BUCKETS = [{"id": "id-documents", "name": "id-documents", "public": True, "file_size_limit": None, "allowed_mime_types": None},
           {"id": "avatars", "name": "avatars", "public": False, "file_size_limit": 1048576, "allowed_mime_types": ["image/png", "image/jpeg"]}]
PROJECT = {"id": "examplerefxyz", "name": "kestrel-bookings", "region": "eu-central-1", "status": "ACTIVE_HEALTHY", "organization_id": "org-kestrel"}

# Requirements each export or answer is evidence for. The oracle concludes on what each artifact shows.
CAPTURES = [
    {"via": "mcp", "file": "advisors.json", "title": "Supabase security advisors", "server": "supabase", "tool": "get_advisors",
     "args": {"type": "security"}, "recipe": "supabase-advisors", "requirements": ["SEC-AC-01", "SEC-AC-05", "SEC-AUTH-02"], "data": ADVISORS},
    {"via": "mcp", "file": "rls.json", "title": "Row-level security status and policies per table", "server": "supabase", "tool": "execute_sql",
     "args": {"query": "select ... from pg_class ... (recipe supabase-rls)"}, "recipe": "supabase-rls", "requirements": ["SEC-AC-01", "SEC-AC-02"], "data": RLS},
    {"via": "mcp", "file": "buckets.json", "title": "Storage buckets and whether they are public", "server": "supabase", "tool": "execute_sql",
     "args": {"query": "select id, name, public from storage.buckets"}, "recipe": "supabase-storage", "requirements": ["SEC-AC-06"], "data": BUCKETS},
    {"via": "mcp", "file": "project.json", "title": "Supabase project region and status", "server": "supabase", "tool": "get_project",
     "args": {}, "recipe": "supabase-project", "requirements": ["SEC-DATA-01", "SEC-DATA-02", "SEC-DATA-03"], "data": PROJECT},
    {"via": "cli", "command": ["git", "log", "--oneline", "-5"], "title": "Recent changes to the repository", "recipe": "github-branch-protection",
     "requirements": ["SEC-OPS-06"]},
    {"via": "export", "file": "auth-settings.txt", "title": "Supabase Authentication settings (screenshots, transcribed)", "recipe": "supabase-auth-settings",
     "requirements": ["SEC-AUTH-01", "SEC-AUTH-03", "SEC-AUTH-04", "SEC-AUTH-06", "SEC-AUTH-07"],
     "data": "Email: Confirm email ON. Rate limits: sign-in 30/5min, sign-up 30/h, email 2/h. Multi-Factor: TOTP available, NOT enforced for admins "
             "(admin accounts listed without MFA factor). Sessions: time-box 7 days, inactivity timeout 24 h. URL configuration: site URL "
             "https://bookings.kestrel.example, redirect allow list contains only that domain. Providers: email only.\n"},
    {"via": "export", "file": "backups.txt", "title": "Supabase Database Backups page (screenshot, transcribed)", "recipe": "supabase-backups",
     "requirements": ["SEC-OPS-01"], "data": "Pro plan. Daily backups, 7 days retained. Point-in-time recovery: enabled (7 days).\n", "roles": ["processor"]},
    {"via": "export", "file": "security-measures.md", "title": "Technical and organizational measures (Kestrel Apps)",
     "requirements": ["SEC-OPS-08", "SEC-OPS-03", "SEC-OPS-04", "SEC-OPS-05", "SEC-CODE-05", "SEC-CODE-06", "SEC-DATA-04", "DP-INV-01", "DP-INV-02",
                      "DP-INV-03", "DP-INV-04", "DP-LIFE-01", "DP-LIFE-03", "DP-LIFE-04", "DP-LIFE-05", "DP-INC-01", "SEC-AC-07", "SEC-AUTH-05",
                      "DP-SUP-02", "DP-SUP-05", "DP-SUP-06", "SEC-OPS-07", "SEC-CODE-04", "SEC-OPS-09", "SEC-CODE-07"],
     "data": ("# Technical and organizational measures\n\nProduction runs on Supabase (EU, Frankfurt). Separate development project with synthetic data. "
              "Admin access: two named engineers, reviewed quarterly, MFA on Supabase, GitHub and Lovable. Logging: Supabase auth and API logs, "
              "alerts on failed logins to the on-call address. Input is validated in edge functions; production builds disable source maps. "
              "Record of processing as processor (Art. 30(2)) kept in the shared drive, version 2026-09. Retention: bookings 3 years, notes 10 years "
              "(professional duty), deleted by a nightly job. Export of a patient's data via the admin console. At contract end all data are "
              "returned as CSV and the project deleted within 30 days, backups expire after 7 days. Incidents are logged in the incident register. "
              "Staff sign a confidentiality agreement. Dependabot alerts are triaged weekly. The client approved the sub-processor list in the DPA "
              "of 2026-02-01. A pre-release review was done with the OWASP checklist in March 2026. Handover documentation lists the architecture "
              "and the RLS design.\n")},
    {"via": "export", "file": "contracts.md", "title": "Sub-processor contracts in place", "recipe": "ai-dpa",
     "requirements": ["DP-SUP-01", "DP-SUP-03", "DP-SUP-04", "DP-AI-03"], "roles": ["processor"],
     "data": ("| Sub-processor | Service | DPA | Transfer mechanism |\n|---|---|---|---|\n| Supabase | database, auth, storage | signed 2026-01-15 | EU hosting |\n"
              "| Lovable | app builder | accepted terms 2026-01-10 | EU-US DPF |\n| OpenAI | note summaries | none | none |\n")},
    {"via": "answer", "file": None, "title": "Restore from backup tested", "question": "Was a restore from backup tested in the last 12 months?",
     "text": "Yes, we restored into a staging project in March 2026 and it worked.", "requirements": ["SEC-OPS-02"], "roles": ["processor"]},
    {"via": "answer", "file": None, "title": "Erasure of a person's data", "question": "Can you erase all data of one person everywhere, including files and AI logs?",
     "text": "Yes, the admin console has a delete-patient function that removes rows and files.", "requirements": ["DP-LIFE-02"]},
    {"via": "answer", "file": None, "title": "Breach notice to the controller", "question": "How fast would you tell the client about a personal data breach?",
     "text": "Within 24 hours by phone and email to the practice manager.", "requirements": ["DP-INC-02"], "roles": ["processor"]},
]

# Planted weaknesses: the unit (REQ-<id>) and the requirement each finding is recorded against.
DEFECTS = [
    {"id": "D1", "requirement": "SEC-CODE-01", "grade": "major", "roles": ["processor", "developer"],
     "note": "A Supabase service-role key is in client code (src/lib/supabase.ts) and bypasses row-level security for anyone who loads the app",
     "note_de": "Ein Supabase-Service-Role-Schlüssel steht im Client-Code (src/lib/supabase.ts) und umgeht die zeilenbasierte Zugriffskontrolle für jeden, der die App lädt"},
    {"id": "D2", "requirement": "SEC-AC-01", "grade": "major", "roles": ["processor", "developer"],
     "note": "Row-level security is disabled on public.treatment_notes, which holds health data",
     "note_de": "Die zeilenbasierte Zugriffskontrolle ist für public.treatment_notes deaktiviert, die Gesundheitsdaten enthält"},
    {"id": "D3", "requirement": "SEC-AC-06", "grade": "major", "roles": ["processor", "developer"],
     "note": "The storage bucket id-documents is public and holds patients' identity documents",
     "note_de": "Der Storage-Bucket id-documents ist öffentlich und enthält Ausweisdokumente von Patienten"},
    {"id": "D4", "requirement": "DP-AI-05", "grade": "minor", "roles": ["processor", "developer"],
     "note": "Treatment notes are sent to OpenAI from the browser, exposing the API key and bypassing server-side limits",
     "note_de": "Behandlungsnotizen werden aus dem Browser an OpenAI gesendet; der API-Schlüssel ist offengelegt und serverseitige Grenzen werden umgangen"},
    {"id": "D5", "requirement": "SEC-AUTH-04", "grade": "minor", "roles": ["processor", "developer"],
     "note": "Multi-factor authentication is not enforced for the app's administrators",
     "note_de": "Für die Administratoren der App ist keine Mehr-Faktor-Authentifizierung erzwungen"},
    {"id": "D6", "requirement": "SEC-AC-03", "grade": "minor", "roles": ["processor", "developer"],
     "note": "The admin page decides access in the browser (profile.role) and reads all bookings with the service-role client",
     "note_de": "Die Admin-Seite entscheidet den Zugriff im Browser (profile.role) und liest alle Buchungen mit dem Service-Role-Client"},
    {"id": "D7", "requirement": "DP-SUP-03", "grade": "major", "roles": ["processor"],
     "note": "OpenAI processes treatment notes without a data processing agreement",
     "note_de": "OpenAI verarbeitet Behandlungsnotizen ohne Auftragsverarbeitungsvertrag"},
]
INQUIRY_ONLY = {"processor": ["SEC-OPS-02", "DP-LIFE-02", "DP-INC-02"], "developer": ["DP-LIFE-02"]}

CONTEXT = {
    "en": {"status": "management-approved", "scope_statement": "The Kestrel Bookings web app and its production environment on Supabase (EU), as of 20 November 2026.",
           "services": "Online booking and treatment notes for a group of physiotherapy practices; AI summaries of treatment notes.",
           "role": "", "boundaries": "Frontend built with Lovable and hosted as a static site; Supabase database, auth and storage; OpenAI for summaries.",
           "sites": [], "outsourced": [], "changes": "", "people": "Two engineers at Kestrel Apps.", "processes": "Changes through GitHub pull requests."},
    "de": {"status": "management-approved", "scope_statement": "Die Web-App Kestrel Bookings und ihre Produktionsumgebung auf Supabase (EU), Stand 20. November 2026.",
           "services": "Online-Terminbuchung und Behandlungsnotizen für eine Gruppe von Physiotherapiepraxen; KI-Zusammenfassungen von Behandlungsnotizen.",
           "role": "", "boundaries": "Mit Lovable erstelltes Frontend als statische Website; Supabase für Datenbank, Authentifizierung und Speicher; OpenAI für Zusammenfassungen.",
           "sites": [], "outsourced": [], "changes": "", "people": "Zwei Entwickler bei Kestrel Apps.", "processes": "Änderungen über GitHub-Pull-Requests."},
}
ROLE_TEXT = {"processor": {"en": "Processor: Kestrel Apps runs the production system for the practice group (the controller).",
                           "de": "Auftragsverarbeiter: Kestrel Apps betreibt das Produktivsystem für die Praxisgruppe (Verantwortlicher)."},
             "developer": {"en": "Developer: the practice group runs the production system; Kestrel Apps built and handed it over.",
                           "de": "Entwickler: Die Praxisgruppe betreibt das Produktivsystem; Kestrel Apps hat es entwickelt und übergeben."}}


def build(case: str) -> None:
    root = OUT / case
    if root.exists():
        shutil.rmtree(root)
    app = root / "app"
    for rel, body in APP_FILES.items():
        (app / rel).parent.mkdir(parents=True, exist_ok=True)
        (app / rel).write_text(body)
    env = {"GIT_AUTHOR_DATE": "2026-03-01T10:00:00", "GIT_COMMITTER_DATE": "2026-03-01T10:00:00"}
    for args in (["init", "-q"], ["add", "."], ["-c", "user.name=Kestrel Dev", "-c", "user.email=dev@kestrel.example", "commit", "-qm", "Initial app"]):
        subprocess.run(["git", "-C", str(app), *args], check=True, env={**__import__("os").environ, **env})

    cfg = {"schema_version": 1, "organization": "Kestrel Apps GmbH", "scope": CONTEXT["en"]["scope_statement"], "auditor": "AI Audit",
           "audit_type": "assessment", "language": "en", "roles": [case], "as_of": AS_OF, "source": {"connector": "intake", "options": {}},
           "management": {"name": "Mara Lindqvist", "title": "Managing Director"}, "sampling_seed": 424242, "signoff": None}
    (root / "engagement.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    for lang in ("en", "de"):
        ctx = dict(CONTEXT[lang], role=ROLE_TEXT[case][lang])
        (root / ("context.yaml" if lang == "en" else "context.de.yaml")).write_text(yaml.safe_dump(ctx, sort_keys=False, allow_unicode=True))

    caps = root / "captures"
    caps.mkdir()
    replay = []
    for c in CAPTURES:
        if case not in c.get("roles", [case]):
            continue
        entry = {k: v for k, v in c.items() if k not in ("data", "roles")}
        if c.get("file"):
            data = c["data"]
            (caps / c["file"]).write_text(json.dumps(data, indent=2) if not isinstance(data, str) else data)
        replay.append(entry)
    (root / "captures.yaml").write_text(yaml.safe_dump(replay, sort_keys=False, allow_unicode=True))

    defects = [d for d in DEFECTS if case in d["roles"]]
    truth = {
        "case": case, "defects": defects, "inquiry_only": INQUIRY_ONLY[case],
        "components": ["web", "supabase", "lovable", "ai"],
        "scan_rules": ["supabase-service-role-key", "ai-sdk-in-client", "client-side-authorization"],
        "subprocessors": ["Supabase", "Lovable", "OpenAI"],
        "out_of_scope": [] if case == "processor" else ["SEC-OPS-01", "SEC-OPS-02", "DP-SUP-03", "DP-INC-02"],
        "acceptable_recommendations": ["not-recommended"],
        "probe": {"tables": ["treatment_notes"], "buckets": ["id-documents"]},
    }
    (root / "truth.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    for case in ("processor", "developer"):
        build(case)
    print(f"Fixtures written to {OUT}")


if __name__ == "__main__":
    main()
