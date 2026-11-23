"""Framework catalogs: loading, recognizing requirement IDs in free text, and matching platform names.

Every catalog lives in `assets/frameworks/<name>.yaml` of each skill (copied from
shared/frameworks by tools/sync.py). Connectors use `finder()` to turn the text a
platform shows ("CC6.1 Logical access", "A.5.15", "Art. 32 GDPR") into catalog IDs.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from . import i18n

# Key of the list of entries in each catalog file.
ENTRIES = {"soc2": "criteria"}

# Lowercase substrings that identify the framework in a compliance platform's framework list.
PLATFORM_NAMES = {
    "soc2": ("soc 2", "soc2"),
    "iso27001": ("27001",),
    "gdpr": ("gdpr", "dsgvo", "general data protection", "2016/679"),
    "nis2": ("nis2", "nis 2", "nis-2", "2022/2555"),
    "app": ("app assessment", "application security"),
}


# Requirements each kind of platform register supports, per framework. Connectors attach
# these to the exports, so a tester finds the risk register under the risk requirements.
HINTS = {
    "soc2": {},
    "iso27001": {
        "findings": ["10.2"], "soa": ["6.1.3"], "risks": ["6.1.2", "8.2"], "treatment": ["6.1.3", "8.3"],
        "obligations": ["A.5.31"], "assets": ["A.5.9"], "data": ["A.5.12"], "audits": ["9.2.1", "9.2.2", "A.5.35"],
        "access_reviews": ["A.5.18"], "access_entries": ["A.5.18", "A.8.2"], "context": ["4.1", "4.2", "4.3"],
        "vendors": ["A.5.19", "A.5.20"],
    },
    "gdpr": {
        "findings": ["Art.33(5)"], "risks": ["Art.24(1)", "Art.32(1)", "Art.32(2)"], "treatment": ["Art.32(1)"],
        "obligations": ["Art.5(2)", "Art.24(1)"], "assets": ["Art.30(1)"], "data": ["Art.30(1)", "Art.30(2)", "Art.5(1)(c)"],
        "audits": ["Art.24(1)", "Art.28(3)(h)", "Art.32(1)(d)"], "access_reviews": ["Art.32(1)(b)", "Art.32(4)"],
        "access_entries": ["Art.32(1)(b)", "Art.32(4)"], "context": ["Art.24(1)", "Art.30(1)"], "vendors": ["Art.28(1)", "Art.28(3)", "Art.44"],
    },
    "nis2": {
        "findings": ["Art.21(4)", "IR.3.6"], "risks": ["Art.21(1)", "Art.21(2)(a)", "IR.2.1"], "treatment": ["Art.21(1)", "IR.2.1"],
        "obligations": ["Art.20(1)", "IR.2.2"], "assets": ["Art.21(2)(i)", "IR.12.4"], "data": ["Art.21(2)(i)", "IR.12.1"],
        "audits": ["Art.21(2)(f)", "IR.2.3", "IR.7.1"], "access_reviews": ["Art.21(2)(i)", "IR.11.2"],
        "access_entries": ["Art.21(2)(i)", "Art.21(2)(j)", "IR.11.2", "IR.11.7"], "context": ["Art.3", "Art.21(1)"],
        "vendors": ["Art.21(2)(d)", "Art.21(3)", "IR.5.2"],
    },
    "app": {
        "findings": ["DP-INC-01"], "risks": ["SEC-OPS-08"], "treatment": ["SEC-OPS-08"], "obligations": ["DP-INV-03"],
        "assets": ["DP-INV-01"], "data": ["DP-INV-01", "DP-INV-02"], "audits": ["SEC-CODE-07"], "access_reviews": ["SEC-AC-07"],
        "access_entries": ["SEC-AC-07", "SEC-AUTH-05"], "context": ["DP-INV-01"], "vendors": ["DP-SUP-01", "DP-SUP-03"],
    },
}

# The organization's description of what is audited: the file each engine reads, and
# the draft a connector writes from the platform's organization context.
DESCRIPTIONS = {
    "soc2": {"file": "system.yaml", "kind": "system", "title": "System description inputs", "requirements": []},
    "iso27001": {"file": "isms.yaml", "kind": "isms", "title": "ISMS scope and context inputs", "requirements": ["4.1", "4.2", "4.3"]},
    "gdpr": {"file": "context.yaml", "kind": "context", "title": "Processing scope and context inputs", "requirements": ["Art.24(1)", "Art.30(1)"]},
    "nis2": {"file": "context.yaml", "kind": "context", "title": "Entity scope and context inputs", "requirements": ["Art.3", "Art.21(1)"]},
    "app": {"file": "context.yaml", "kind": "context", "title": "Application scope and context inputs", "requirements": ["DP-INV-01"]},
}


def draft_description(name: str, ctx: dict) -> dict:
    """A draft description from a platform's organization context (product, customers,
    architecture, team, processes). The organization completes it before it is printed."""
    ctx = ctx or {}
    if name == "soc2":
        return {
            "status": "draft", "overview": ctx.get("product") or "", "services": ctx.get("customers") or "", "commitments": [],
            "components": {"infrastructure": ctx.get("architecture") or "", "software": "", "people": ctx.get("team") or "",
                           "procedures": ctx.get("processes") or "", "data": ""},
            "subservice_organizations": [], "cuecs": [], "incidents": "", "changes": "",
        }
    if name == "iso27001":
        return {
            "status": "draft", "scope_statement": "", "boundaries": ctx.get("architecture") or "", "sites": [],
            "context": "\n\n".join(x for x in (ctx.get("product"), ctx.get("customers")) if x), "interested_parties": [],
            "interfaces": "", "outsourced": [], "soa_version": "", "changes": "",
            "people": ctx.get("team") or "", "processes": ctx.get("processes") or "",
        }
    return {
        "status": "draft", "scope_statement": "", "services": "\n\n".join(x for x in (ctx.get("product"), ctx.get("customers")) if x),
        "role": "", "boundaries": ctx.get("architecture") or "", "sites": [], "outsourced": [], "changes": "",
        "people": ctx.get("team") or "", "processes": ctx.get("processes") or "",
    }


class Framework:
    """What connectors and engines need to know about the audited framework.

    `name` is the catalog (soc2, iso27001, gdpr, nis2). `description` says which
    file holds the organization's description of what is audited:
    {file, kind, title, requirements}. `soa` is set when applicability comes from a
    Statement of Applicability (ISO 27001).
    """

    def __init__(self, frameworks_dir: Path, name: str, description: dict | None = None, soa: dict | None = None):
        self.dir = frameworks_dir
        self.name = name
        self.description = description or DESCRIPTIONS[name]
        self.soa = soa
        self._find = None

    def hint(self, topic: str) -> list[str]:
        """Requirement IDs a platform register of this topic supports (empty when none)."""
        return list(HINTS.get(self.name, {}).get(topic, []))

    def draft_description(self, ctx: dict) -> dict:
        return draft_description(self.name, ctx)

    def find(self, *texts, annex: bool | None = None) -> list[str]:
        if self._find is None:
            self._find = finder(self.dir, self.name)
        return self._find(*texts, annex=annex)

    def matches_platform(self, platform_framework_name: str) -> bool:
        return matches_platform(self.name, platform_framework_name)

    def entries(self, lang: str = i18n.DEFAULT) -> list[dict]:
        return entries(self.dir, self.name, lang)


def entries_key(name: str) -> str:
    return ENTRIES.get(name, "requirements")


def load(frameworks_dir: Path, name: str, lang: str = i18n.DEFAULT) -> dict:
    return i18n.load_catalog(frameworks_dir, name, lang, entries=entries_key(name))


def entries(frameworks_dir: Path, name: str, lang: str = i18n.DEFAULT) -> list[dict]:
    return load(frameworks_dir, name, lang)[entries_key(name)]


def matches_platform(name: str, platform_framework_name: str) -> bool:
    low = (platform_framework_name or "").lower()
    return any(k in low for k in PLATFORM_NAMES.get(name, (name,)))


# --- recognizing IDs in text -------------------------------------------------------

# SOC 2: CC6.1, A1.2, C1.1, PI1.3, P6.7.
SOC2_RE = re.compile(r"\b(CC[1-9]\.[0-9]|A1\.[1-3]|C1\.[12]|PI1\.[1-5]|P[1-8]\.[1-7])\b")
# ISO 27001 Annex A written explicitly: A.5.15, A 5.15, A5.15, "Annex A 5.15".
ANNEX_RE = re.compile(r"\bA\s?\.?\s?([5-8])\.(\d{1,2})(?![\d.])")
# A bare clause or control number: 4.1, 6.1.2, 9.2, 8.24. Not part of a longer number.
NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,2})\.(\d{1,2})(?:\.(\d))?(?![\d]|\.\d)")
# EU law articles: Art. 32, Art 32(1)(a), Article 21 (2) (d), Artikel 33 Abs. 1.
ARTICLE_RE = re.compile(r"\b(?:Art(?:icle|ikel)?\.?)\s*(\d{1,3})((?:\s*\(\s*[0-9a-z]{1,4}\s*\))*)(?:\s*Abs\.?\s*(\d{1,2}))?", re.I)
# App catalog IDs: SEC-AC-01, DP-SUP-03.
APP_RE = re.compile(r"\b(?:SEC|DP)-[A-Z]{2,4}-\d{2}\b")
# NIS2 Implementing Regulation (EU) 2024/2690 annex sections: IR.1.1, IR 3.2.
IR_RE = re.compile(r"\bIR\s?\.?\s?(\d{1,2}\.\d{1,2})\b")


def finder(frameworks_dir: Path, name: str):
    """A function `find(*texts, annex=None) -> [ids]` for the named catalog."""
    ids = tuple(str(e["id"]) for e in entries(frameworks_dir, name))
    if name == "soc2":
        return _find_soc2
    if name == "iso27001":
        kinds = {str(e["id"]): e.get("kind") for e in entries(frameworks_dir, name)}
        clauses = frozenset(i for i, k in kinds.items() if k == "clause")
        controls = frozenset(i for i, k in kinds.items() if k == "annex")
        return lambda *texts, annex=None: _find_iso(texts, clauses, controls, annex)
    if name == "app":
        known = frozenset(ids)
        return lambda *texts, annex=None: [x for x in dict.fromkeys(m for t in _texts(texts) for m in APP_RE.findall(t)) if x in known]
    return lambda *texts, annex=None: _find_articles(texts, ids)


def _texts(texts) -> list[str]:
    import json

    out = []
    for text in texts:
        if text:
            out.append(text if isinstance(text, str) else json.dumps(text))
    return out


def _add(found: list[str], x: str) -> None:
    if x not in found:
        found.append(x)


def _find_soc2(*texts, annex=None) -> list[str]:
    found: list[str] = []
    for text in _texts(texts):
        for match in SOC2_RE.findall(text):
            _add(found, match)
    return found


def _find_iso(texts, clauses: frozenset, controls: frozenset, annex: bool | None) -> list[str]:
    """ISO/IEC 27001:2022 requirement IDs mentioned in free text, in order.

    `A.5.15` is always Annex A. A bare `5.15` is ambiguous between a clause and an
    Annex A control: annex=True says the text is an Annex A reference, annex=False
    a clause. Left as None, a bare number is a clause when one exists (5.1
    Leadership and commitment) and an Annex A control otherwise (8.24). A parent
    clause expands to its sub-clauses: 9.2 becomes 9.2.1 and 9.2.2.
    """
    found: list[str] = []
    for text in _texts(texts):
        for m in ANNEX_RE.finditer(text):
            rid = f"A.{m.group(1)}.{m.group(2)}"
            if rid in controls:
                _add(found, rid)
        rest = ANNEX_RE.sub(" ", text)
        for m in NUMBER_RE.finditer(rest):
            num = ".".join(g for g in m.groups() if g)
            as_annex = f"A.{m.group(1)}.{m.group(2)}" if not m.group(3) else ""
            children = sorted(c for c in clauses if c.startswith(num + "."))
            if annex is True and as_annex in controls:
                _add(found, as_annex)
            elif annex is not False and num not in clauses and not children and as_annex in controls:
                _add(found, as_annex)
            elif num in clauses:
                _add(found, num)
            elif children and annex is not True:
                for c in children:
                    _add(found, c)
    return found


def _find_articles(texts, ids: tuple[str, ...]) -> list[str]:
    """Article references (GDPR, NIS2) and IR sections, matched to the catalog's IDs.

    An exact ID wins ("Art.32(1)(a)"). A reference to a whole article or paragraph
    expands to the catalog entries under it ("Art. 32" -> every Art.32 entry). A
    reference more specific than the catalog falls back to the nearest parent.
    """
    known = set(ids)
    found: list[str] = []
    for text in _texts(texts):
        for m in ARTICLE_RE.finditer(text):
            parts = re.findall(r"\(\s*([0-9a-z]{1,4})\s*\)", m.group(2) or "", flags=re.I)
            if m.group(3):
                parts = [m.group(3)] + parts
            rid = f"Art.{m.group(1)}" + "".join(f"({p.lower()})" for p in parts)
            for x in _resolve(rid, ids, known):
                _add(found, x)
        for m in IR_RE.finditer(text):
            rid = f"IR.{m.group(1)}"
            if rid in known:
                _add(found, rid)
    return found


def _resolve(rid: str, ids: tuple[str, ...], known: set[str]) -> list[str]:
    if rid in known:
        return [rid]
    children = [i for i in ids if i.startswith(rid + "(")]
    if children:
        return children
    while "(" in rid:
        rid = rid[: rid.rindex("(")]
        if rid in known:
            return [rid]
    return []
