# Copied from shared/lib/connectors/intake.py by tools/sync.py. Edit that file, not this copy.
"""Intake connector: add what the agent captured (`capture` command) to the bundle.

Reads `intake/` in the engagement folder (or `source.options.path`): MCP tool
responses, read-only CLI output, exports and screenshots the user provided, and
answers. Each becomes an evidence artifact with its evidence tier:

  mcp, cli  -> obtained: captured  (the agent pulled it, the call is recorded)
  export    -> obtained: client    (the organization provided it)
  answer    -> obtained: inquiry   (the organization said so; never enough on its own)
  scan      -> obtained: direct    (detect's code scan: a script read the repository)
  probe     -> obtained: direct    (an active read-only check of the live system, e.g. anonymous access)

The capture record (server, tool, arguments or command, time, who) is kept on the
artifact, so a reviewer can repeat the call. Use it next to a source that provides
the control matrix (records, probo ...), or alone: then every requirement is
assessed directly.
"""

from __future__ import annotations

from pathlib import Path

from ..bundle import BundleWriter
from ..capture import TIERS, entries
from ..io import AuditError


def pull(writer: BundleWriter, options: dict, engagement) -> None:
    root = Path(options.get("path", ".")) if options.get("path") else engagement.root
    if not root.is_absolute():
        root = engagement.root / root
    items = entries(root)
    if not items:
        writer.warn(f"intake: nothing captured yet in {root / 'intake'}; use the capture command, then ingest --replace")
        return
    known = {str(e["id"]) for e in writer.framework.entries()} if writer.framework else set()
    for path, meta in items:
        if not path.exists():
            raise AuditError(f"intake: {path.name} is listed in its .meta.json but missing; captures are never deleted")
        unknown = [r for r in meta.get("requirements") or [] if known and r not in known]
        if unknown:
            writer.warn(f"intake/{path.name}: unknown requirement IDs {unknown}")
        record = {k: meta[k] for k in ("via", "server", "tool", "args", "command", "exit_code", "at", "by", "recipe", "request",
                                       "question", "original_name") if meta.get(k) not in (None, "", {}, [])}
        writer.add_file(path, title=meta["title"], kind="evidence", controls=meta.get("controls") or [],
                        requirements=[r for r in meta.get("requirements") or [] if not known or r in known],
                        date=(meta.get("at") or "")[:10] or None, obtained=TIERS[meta["via"]],
                        source_ref=f"intake/{path.name}", capture=record)
    writer.source = f"{root / 'intake'} ({len(items)} captures)"
