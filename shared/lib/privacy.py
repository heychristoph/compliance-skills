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
PERSON_KEYS = {"full_name", "employee", "candidate", "requester", "author"}
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
        text = path.read_text(encoding="utf-8", errors="replace")
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
        if path.parent.name == "populations" and path.stem in ("hires", "terminations"):
            for row in csv.DictReader(text.splitlines()):
                _add_person(row.get("name") or "", found)
    allowed = {n for n in allowed if n}
    tokens = {word.casefold() for name in allowed for word in re.split(r"[^A-Za-z]+", name) if len(word) > 2}
    kept = set()
    for name in found:
        if any(name.casefold() == a.casefold() or name.casefold() in a.casefold() for a in allowed):
            continue
        first = name.split()[0].casefold() if name.split() else ""
        if first and first in tokens:
            continue
        kept.add(name)
    return kept


def redact(text: str, names: set[str]) -> str:
    """Replace a leaked email, phone number or person in a report index entry."""
    if not text:
        return text
    cleaned = EMAIL.sub("[redacted]", text)
    cleaned = PHONE.sub("[redacted]", cleaned)
    for name in sorted(names, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(name)}\b", "[redacted]", cleaned, flags=re.I)
    return cleaned


def leaks(text: str, names: set[str]) -> list[str]:
    found = []
    for match in EMAIL.finditer(text):
        found.append(f"contains the email address {match.group(0)}.")
    for match in PHONE.finditer(text):
        found.append(f"contains the phone number {match.group(0)}.")
    low = text.casefold()
    for name in sorted(names):
        if re.search(rf"\b{re.escape(name)}\b", low, flags=re.I):
            found.append(f"names {name}.")
    return found


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


def _walk(obj, found: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in PERSON_KEYS and isinstance(value, str):
                _add_person(value, found)
            else:
                _walk(value, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, found)


def _add_person(value: str, found: set[str]) -> None:
    value = value.strip()
    if PERSON.match(value):
        found.add(value)
