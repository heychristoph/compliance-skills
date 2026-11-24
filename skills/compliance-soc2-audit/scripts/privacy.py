"""What a customer report may identify.

Workpapers keep names, inboxes and phone numbers, because those are the audit
record. The PDF does not. It may name the assertion signer and organizations.
It may not name anyone else, and it may not contain an email address or a phone
number. `validate --final` and `render` both use this module. The detection is
shared by every audit engine (common/privacy.py); this module says which strings
reach the SOC 2 report and which names it may print.
"""

from __future__ import annotations

from common import privacy as shared
from core import Engagement


def activity(eng: Engagement, wp: dict) -> str:
    """Control wording printed in the report. Never the source description."""
    return shared.activity(eng, wp)


def report_system(eng: Engagement) -> dict | None:
    """Description printed in Section III: management's system.yaml, or an approved source file."""
    return shared.printable(eng, "system.yaml")


def fragments(eng: Engagement) -> list[tuple[str, str]]:
    """Every string that can reach the PDF, with a label for the error."""
    out = []
    cfg = eng.config
    mgmt = cfg.get("management") or {}
    out += [("engagement service organization", cfg.get("service_organization") or ""), ("engagement system", cfg.get("system") or ""),
            ("management title", mgmt.get("title") or ""), ("sign-off model", (cfg.get("signoff") or {}).get("model") or "")]
    out += [(f"subservice organization {s.get('name')}", shared.flatten(s)) for s in cfg.get("subservice_organizations") or []]
    system = report_system(eng)
    if system:
        out.append(("system description", shared.flatten(system)))
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
        for exc in wp.get("exceptions") or []:
            out.append((f"{cid} exception", exc.get("description") or ""))
            if exc.get("management_response"):
                out.append((f"{cid} management response", exc["management_response"]))
    if eng.opinion_path.exists():
        from core import load_json
        opinion = load_json(eng.opinion_path)
        if opinion.get("basis"):
            out.append(("opinion basis", opinion["basis"]))
        for item in opinion.get("scope_limitations") or []:
            out.append(("opinion scope limitation", item))
    return [(label, text) for label, text in out if text and text.strip()]


def check(eng: Engagement) -> tuple[list[str], list[str]]:
    """Errors name the string that would identify someone. Warnings cover a missing description."""
    errors = []
    warnings = []
    if report_system(eng) is None:
        warnings.append(
            "Section III does not include a system description. The source draft is evidence and is not printed. "
            "Write system.yaml at the engagement root for readers of the report. Name no one but management.name, "
            "and include no email address or phone number."
        )
    forbidden = _forbidden(eng)
    for label, text in fragments(eng):
        for hit in shared.leaks(text, forbidden):
            errors.append(f"{label}: {hit} The customer report does not identify that person. Keep it in the workpaper observations.")
    return errors, warnings


def guard(eng: Engagement, data: dict) -> None:
    """Last gate before the PDF: no string of the assembled report may identify a person or hold contact details."""
    from core import AuditError

    hits = shared.scan(data, _forbidden(eng))
    if hits:
        raise AuditError("The report would identify someone or show contact details:\n  " + "\n  ".join(hits[:20])
                         + "\nFix the source (workpaper, opinion, system.yaml or engagement.yaml), then render again.")


def redact(text: str, eng: Engagement) -> str:
    """Replace a leaked email, phone number or person in a report index entry."""
    if not text:
        return text
    return shared.redact(text, _forbidden(eng))


def _forbidden(eng: Engagement) -> set[str]:
    """People the bundle identifies, minus the assertion signer and organization names."""
    return shared.forbidden(eng.bundle, "system.yaml", _allowed(eng))


def _allowed(eng: Engagement) -> set[str]:
    cfg = eng.config
    names = {cfg.get("service_organization") or "", cfg.get("system") or ""}
    mgmt = (cfg.get("management") or {}).get("name") or ""
    if mgmt:
        names.add(mgmt)
    for sub in cfg.get("subservice_organizations") or []:
        names.add(sub.get("name") or "")
    names |= shared.vendor_names(eng.bundle)
    return {n for n in names if n}
