"""Finding people in an evidence bundle, so a report never identifies them.

Workpapers keep names, inboxes and phone numbers, because those are the audit
record. The PDF does not: it may name the organizations and the one person whose
name the engagement prints (the assertion signer or representative), and nothing
else that identifies someone. Each engine decides which strings reach its PDF and
which names are allowed; this module finds the people and the leaks.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

from .io import load_yaml

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?:\+\d{8,15}\b|\(\d{3}\)\s*\d{3}[-.]\d{4}\b|\b\d{3}[-.)]\s*\d{3}[-.]\d{4}\b)")
PERSON = re.compile(r"^[A-Z][a-z]{2,} [A-Z][a-z]{2,}$")
# A given name and surname sitting where prose introduces a person.
INTRODUCED = re.compile(
    r"\b([A-Z][a-z]{2,} [A-Z][a-z]{2,})"
    r"(?="
    r", (?:intern|founder|employee|contractor|director|officer|analyst|engineer|owner)\b"
    r"| wrote\b| emailed\b| said\b"
    r"| \((?!EU\b|EC\b|\d)"   # "Dana Leaver (" introduces a person; "Regulation (EU)" and "(2024)" do not
    r")"
)
BY_NAME = re.compile(r"\bby ([A-Z][a-z]{2,} [A-Z][a-z]{2,})\b")
# JSON keys whose value is a person's name (platform exports, git history).
# Field names compared without case or separators ("Full Name", "fullName", "full_name" are one key).
PERSON_KEYS = {"fullname", "employee", "employeename", "candidate", "requester", "author", "displayname", "personname", "contactname"}
GIVEN_KEYS = {"firstname", "givenname", "forename", "first", "vorname"}
FAMILY_KEYS = {"lastname", "familyname", "surname", "last", "nachname"}
EMAIL_KEYS = {"email", "emailaddress", "mail", "workemail"}
GENERIC_LOCAL = {"security", "support", "admin", "info", "noreply", "no-reply", "hello", "contact", "privacy", "legal", "sales", "billing", "postmaster"}
TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".yaml", ".yml"}


def activity(eng, wp: dict) -> str:
    """Control wording printed in the report: the workpaper statement or the control title, never the source description."""
    statement = (wp.get("statement") or "").strip()
    if statement:
        return statement
    for control in eng.controls:
        if control["id"] == wp["control_id"] and (control.get("title") or "").strip():
            return control["title"].strip()
    return wp["control_id"]


def printable(eng, filename: str) -> dict | None:
    """The description a report may print.

    A draft pulled from the compliance system is evidence, not the text readers see.
    The organization's file at the engagement root is printed, and so is a source
    file only when it is already marked management-approved.
    """
    root = eng.root / filename
    if root.exists():
        return load_yaml(root)
    bundled = eng.bundle / filename
    if bundled.exists():
        data = load_yaml(bundled)
        if data.get("status") == "management-approved":
            return data
    return None


def vendor_names(bundle: Path) -> set[str]:
    vendors = bundle / "populations" / "vendors.csv"
    if not vendors.exists():
        return set()
    return {row.get("name") or "" for row in csv.DictReader(vendors.read_text(encoding="utf-8", errors="replace").splitlines())}


def forbidden(bundle: Path, description_file: str, allowed: set[str]) -> set[str]:
    """People the bundle identifies, minus the allowed names (organizations, the signer)."""
    found: set[str] = set()
    if not bundle.exists():
        return set()
    for path in bundle.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace").removeprefix("\ufeff")  # Excel's UTF-8 BOM
        for match in EMAIL.finditer(text):
            local = match.group(0).split("@", 1)[0].lower()
            if re.fullmatch(r"[a-z]{9,}", local) and local not in GENERIC_LOCAL:
                found.add(local)
        if path.parent == bundle and path.name == description_file:
            _harvest_prose(text, found)
        if path.parent == bundle and path.name == "controls.csv":
            for row in csv.DictReader(text.splitlines()):
                _harvest_prose(row.get("description") or "", found)
        if path.suffix.lower() == ".json":
            try:
                _walk(json.loads(text), found)
            except json.JSONDecodeError:
                pass
        if path.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml

                _walk(yaml.safe_load(text), found)
            except Exception:  # an unparsable file is still scanned for emails above
                pass
        if path.parent.name == "populations" and path.stem in ("hires", "terminations"):
            for row in csv.DictReader(text.splitlines()):
                _add_named(row.get("name") or "", found)
        if path.suffix.lower() == ".csv":
            # Every CSV, populations included (an HR list with full_name, first_name/last_name, email, ...):
            # the same person fields as JSON and YAML.
            try:
                _walk(list(csv.DictReader(text.splitlines())), found)
            except csv.Error:
                pass
    allowed = {n for n in allowed if n}
    exact = {fold(a) for a in allowed}
    squashed = {re.sub(r"[^a-z]", "", fold(a)) for a in allowed}  # "maralindqvist" for an email local part
    kept = set()
    for name in found:
        key = fold(name)
        # Only the allowed identities themselves are exempt (the named representative, the organizations and
        # vendors). Sharing a first name or a word with one of them exempts nobody.
        if key in exact or (" " not in key and key in squashed):
            continue
        # Part of an allowed organization's name ("Web Services" in "Amazon Web Services"), as whole words.
        if " " in key and any(re.search(rf"\b{re.escape(key)}\b", a) for a in exact):
            continue
        kept.add(name)
    return kept


def fold(text: str) -> str:
    """Unicode-normalized, case-folded text, so 'Groß', 'GROSS' and 'gross' (or a decomposed 'é') compare equal."""
    return unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold())


def _named(name: str, text: str) -> bool:
    """Whether a person's name appears in the text as whole words, after folding both sides."""
    return re.search(rf"(?<!\w){re.escape(fold(name))}(?!\w)", fold(text)) is not None


def redact(text: str, names: set[str]) -> str:
    """Replace a leaked email, phone number or person in a report index entry."""
    if not text:
        return text
    cleaned = EMAIL.sub("[redacted]", text)
    cleaned = PHONE.sub("[redacted]", cleaned)
    for name in sorted(names, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(name)}\b", "[redacted]", cleaned, flags=re.I)
        if _named(name, cleaned):  # a spelling the plain match missed ('Gross' for 'Groß'): drop the whole entry
            return "[redacted]"
    return cleaned


def leaks(text: str, names: set[str]) -> list[str]:
    found = []
    for match in EMAIL.finditer(text):
        found.append(f"contains the email address {match.group(0)}.")
    for match in PHONE.finditer(text):
        found.append(f"contains the phone number {match.group(0)}.")
    for name in sorted(names):
        if _named(name, text):
            found.append(f"names {name}.")
    return found


def scan(obj, names: set[str], where: str = "report") -> list[str]:
    """Every leak in a nested structure of strings (the assembled report data), with its location."""
    hits = []
    if isinstance(obj, str):
        hits += [f"{where}: {h}" for h in leaks(obj, names)]
    elif isinstance(obj, dict):
        for k, v in obj.items():
            hits += scan(v, names, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += scan(v, names, f"{where}[{i}]")
    return hits


def flatten(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(flatten(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(flatten(v) for v in value)
    return ""


def _harvest_prose(text: str, found: set[str]) -> None:
    """Names introduced in the description or a control description."""
    for match in INTRODUCED.finditer(text):
        found.add(match.group(1))
    for match in BY_NAME.finditer(text):
        found.add(match.group(1))


def _key(key) -> str:
    return re.sub(r"[^a-z]", "", str(key).lower())


def _walk(obj, found: set[str]) -> None:
    if isinstance(obj, dict):
        fields = {_key(k): v for k, v in obj.items() if isinstance(v, str)}
        # A people register (records connector, HR export): a `name` next to an email address is a person,
        # whether or not they joined or left in the period.
        if fields.get("name") and any("@" in fields.get(k, "") for k in EMAIL_KEYS):
            _add_named(fields["name"], found)
        # Given and family name in separate fields (first_name, last_name): the person is both together.
        given = next((fields[k] for k in GIVEN_KEYS if fields.get(k)), "")
        family = next((fields[k] for k in FAMILY_KEYS if fields.get(k)), "")
        if given.strip() and family.strip():
            _add_named(f"{given} {family}", found)
        for key, value in obj.items():
            if _key(key) in PERSON_KEYS and isinstance(value, str):
                _add_named(value, found)
            else:
                _walk(value, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, found)


def _add_person(value: str, found: set[str]) -> None:
    """A name from free text: only the clear "Given Family" shape, to avoid flagging ordinary words."""
    value = value.strip()
    if PERSON.match(value):
        found.add(value)


def _add_named(value: str, found: set[str]) -> None:
    """A name from a field that holds a person (full_name, a people register): any spelling counts,
    accents, particles and short names included (José García, Dana van Dijk, Li Wu)."""
    value = " ".join(str(value).split())
    if 2 <= len(value) <= 80 and "@" not in value and any(ch.isalpha() for ch in value) and not any(ch.isdigit() for ch in value):
        found.add(value)
