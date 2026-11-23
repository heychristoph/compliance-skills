# Copied from shared/engines/requirements/privacy.py by tools/sync.py. Edit that file, not this copy.
"""What the audit report may identify.

Workpapers keep names, inboxes and phone numbers, because those are the audit
record. The PDF does not. It may name the organization's representative and
organizations. It may not name anyone else, and it may not contain an email
address or a phone number. `validate --final` and `render` both use this module.
The detection is shared by every audit engine (common/privacy.py); this module
says which strings reach this engine's report and which names it may print.
"""

from __future__ import annotations

from common import privacy as shared
from core import DESCRIPTION, Engagement, load_json, load_yaml


def activity(eng: Engagement, wp: dict) -> str:
    """Control wording printed in the report. Never the source description."""
    return shared.activity(eng, wp)


def report_description(eng: Engagement) -> dict | None:
    """The organization's description printed in Section II: the file at the engagement root, or an approved source file."""
    return shared.printable(eng, DESCRIPTION["file"])


def fragments(eng: Engagement) -> list[tuple[str, str]]:
    """Every string that can reach the PDF, with a label for the error."""
    out = []
    cfg = eng.config
    mgmt = cfg.get("management") or {}
    out += [("engagement organization", cfg.get("organization") or ""), ("engagement scope", cfg.get("scope") or ""),
            ("management title", mgmt.get("title") or ""), ("sign-off model", (cfg.get("signoff") or {}).get("model") or "")]
    stack = eng.review / "stack.yaml"
    if stack.exists():
        out.append(("sub-processors (review/stack.yaml)", shared.flatten(load_yaml(stack).get("subprocessors") or [])))
    desc = report_description(eng)
    if desc:
        out.append((DESCRIPTION["label"], shared.flatten(desc)))
    for cid, wp in sorted(eng.load_workpapers().items()):
        out.append((f"{cid} report wording", activity(eng, wp)))
        for procedure in wp.get("procedures") or []:
            out.append((f"{cid} procedure", procedure.get("text") or ""))
        if wp.get("scope_limitation"):
            out.append((f"{cid} scope limitation", wp["scope_limitation"]))
        rationale = (wp.get("design") or {}).get("rationale") or ""
        if rationale:
            out.append((f"{cid} design rationale", rationale))
        for item in wp.get("items") or []:
            if item.get("note"):
                out.append((f"{cid} sample note", item["note"]))
        for dev in wp.get("deviations") or []:
            out.append((f"{cid} deviation", dev.get("description") or ""))
    if eng.findings_path.exists():
        doc = load_json(eng.findings_path)
        for key in ("summary", "scope_note"):
            if doc.get(key):
                out.append((f"findings {key}", doc[key]))
        for item in doc.get("scope_limitations") or []:
            out.append(("findings scope limitation", item))
        for f in doc.get("findings") or []:
            for key in ("statement", "objective_evidence", "management_response"):
                if f.get(key):
                    out.append((f"{f.get('id')} {key.replace('_', ' ')}", f[key]))
    return [(label, text) for label, text in out if text and text.strip()]


def check(eng: Engagement) -> tuple[list[str], list[str]]:
    """Errors name the string that would identify someone. Warnings cover a missing description."""
    errors = []
    warnings = []
    if report_description(eng) is None:
        warnings.append(
            f"Section II does not include the {DESCRIPTION['label']}. The source draft is evidence and is not printed. "
            f"Write {DESCRIPTION['file']} at the engagement root for readers of the report. Name no one but management.name, "
            "and include no email address or phone number."
        )
    forbidden = _forbidden(eng)
    for label, text in fragments(eng):
        for hit in shared.leaks(text, forbidden):
            errors.append(f"{label}: {hit} The audit report does not identify that person. Keep it in the workpaper observations.")
    return errors, warnings


def guard(eng: Engagement, data: dict) -> None:
    """Last gate before the PDF: no string of the assembled report may identify a person or hold contact details."""
    from core import AuditError

    hits = shared.scan(data, _forbidden(eng))
    if hits:
        raise AuditError("The report would identify someone or show contact details:\n  " + "\n  ".join(hits[:20])
                         + "\nFix the source (workpaper, findings, description or engagement.yaml), then render again.")


def redact(text: str, eng: Engagement) -> str:
    """Replace a leaked email, phone number or person in a report index entry."""
    if not text:
        return text
    return shared.redact(text, _forbidden(eng))


def _forbidden(eng: Engagement) -> set[str]:
    """People the bundle identifies, minus the representative and organization names."""
    return shared.forbidden(eng.bundle, DESCRIPTION["file"], _allowed(eng))


def _allowed(eng: Engagement) -> set[str]:
    cfg = eng.config
    names = {cfg.get("organization") or ""}
    mgmt = (cfg.get("management") or {}).get("name") or ""
    if mgmt:
        names.add(mgmt)
    for supplier in (eng.description or {}).get("outsourced") or []:
        if isinstance(supplier, dict):
            names.add(supplier.get("name") or "")
    names |= shared.vendor_names(eng.bundle)
    return {n for n in names if n}
