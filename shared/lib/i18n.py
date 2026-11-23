"""Languages for framework catalogs and reports.

A framework catalog is one English file, `assets/frameworks/<name>.yaml`, plus one
overlay per other language, `assets/frameworks/<lang>/<name>.yaml`:

    language: de
    framework: {name: ..., title: ...}       # merged over the base `framework` block
    groups: {<group key>: <name>}            # replaces group names
    categories: {<key>: {name: ...}}         # merged over base categories (SOC 2)
    items: {<id>: {title, summary, evidence, text}}   # merged over the base entry with that id

Only text is translated. IDs, kinds, plans and mappings always come from the base,
so a translation can never change what is audited.

Report wording lives in each skill's `assets/report/text/<lang>.yaml`.
"""

from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import yaml

LANGUAGES = ("en", "de")
DEFAULT = "en"

# Fields an overlay may set on an entry. Anything else in an overlay is ignored.
TEXT_FIELDS = ("title", "summary", "evidence", "text")

_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
           "November", "Dezember"],
}
_AND = {"en": "and", "de": "und"}


class LanguageError(ValueError):
    pass


def check(lang: str | None) -> str:
    lang = (lang or DEFAULT).strip().lower()
    if lang not in LANGUAGES:
        raise LanguageError(f"Unsupported language '{lang}'. Supported: {', '.join(LANGUAGES)}.")
    return lang


def fmt_date(d: dt.date, lang: str = DEFAULT, day_first: bool = False) -> str:
    """June 30, 2026 (en), 30 June 2026 (en, day_first, as ISO reports write it) or 30. Juni 2026 (de)."""
    lang = check(lang)
    month = _MONTHS[lang][d.month - 1]
    if lang == "de":
        return f"{d.day}. {month} {d.year}"
    return f"{d.day} {month} {d.year}" if day_first else f"{month} {d.day}, {d.year}"


def join(names: list[str], lang: str = DEFAULT) -> str:
    """a and b; a, b, and c (en, serial comma); a, b und c (de, no comma before und)."""
    lang = check(lang)
    word = _AND[lang]
    if len(names) <= 2:
        return f" {word} ".join(names)
    comma = "," if lang == "en" else ""
    return ", ".join(names[:-1]) + f"{comma} {word} " + names[-1]


def _read(path: Path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_catalog(frameworks_dir: Path, name: str, lang: str = DEFAULT, entries: str = "requirements") -> dict:
    """The base catalog with the language overlay merged in.

    `entries` is the key of the list of items in the base file (`requirements`, or
    `criteria` for SOC 2). A missing overlay or a missing item falls back to English.
    """
    lang = check(lang)
    base = _read(frameworks_dir / f"{name}.yaml")
    if lang == DEFAULT:
        return base
    path = frameworks_dir / lang / f"{name}.yaml"
    if not path.exists():
        return base
    over = _read(path)
    out = copy.deepcopy(base)
    out["language"] = lang
    if isinstance(out.get("framework"), dict):
        out["framework"].update({k: v for k, v in (over.get("framework") or {}).items() if k != "id"})
    if isinstance(out.get("groups"), dict):
        out["groups"].update({k: v for k, v in (over.get("groups") or {}).items() if k in out["groups"]})
    if isinstance(out.get("categories"), dict):
        for key, value in (over.get("categories") or {}).items():
            if key in out["categories"]:
                out["categories"][key] = {**out["categories"][key], **value}
    items = over.get("items") or {}
    group_names = over.get("groups") or {}
    for entry in out.get(entries) or []:
        entry.update({k: v for k, v in (items.get(str(entry["id"])) or {}).items() if k in TEXT_FIELDS})
        # SOC 2 entries name their group in English text; translate that name too.
        if isinstance(entry.get("group"), str) and entry["group"] in group_names and "groups" not in base:
            entry["group"] = group_names[entry["group"]]
    return out


def missing(frameworks_dir: Path, name: str, lang: str, entries: str = "requirements") -> list[str]:
    """IDs in the base catalog without text in the overlay (for tests and `sync --check`)."""
    base = _read(frameworks_dir / f"{name}.yaml")
    path = frameworks_dir / lang / f"{name}.yaml"
    if not path.exists():
        return [f"{name}: no {lang} overlay"]
    items = _read(path).get("items") or {}
    return [str(e["id"]) for e in base.get(entries) or [] if str(e["id"]) not in items]
