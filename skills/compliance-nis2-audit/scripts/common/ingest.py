# Copied from shared/lib/ingest.py by tools/sync.py. Edit that file, not this copy.
"""`ingest` for every audit engine: pull each configured source into one evidence bundle.

An engagement names one source (`source: {connector, options}`) or several
(`sources: [...]`), for example a compliance-prep records folder for the documents
plus `intake` for what the agent captured from MCP servers, CLI tools, exports and
answers. All sources write through one BundleWriter, so artifact IDs run on across
sources and the manifest lists every artifact once.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil

from . import connectors
from .bundle import BundleWriter
from .io import AuditError


def sources(config: dict) -> list[dict]:
    """The engagement's sources, whichever form engagement.yaml uses."""
    if config.get("sources"):
        return [dict(s) for s in config["sources"]]
    return [dict(config["source"])] if config.get("source") else []


def parse_options(connector_names: list[str], options: list[str] | None) -> list[dict]:
    """`init --connector a --connector b --option key=value --option b.key=value` into source entries.

    An option without a `<connector>.` prefix belongs to the first connector.
    """
    entries = [{"connector": name, "options": {}} for name in connector_names]
    by_name = {e["connector"]: e for e in entries}
    for raw in options or []:
        if "=" not in raw:
            raise AuditError(f"--option {raw}: use key=value or <connector>.key=value")
        key, value = raw.split("=", 1)
        prefix, _, rest = key.partition(".")
        if rest and prefix in by_name:
            by_name[prefix]["options"][rest] = value
        else:
            entries[0]["options"][key] = value
    return entries


def run(eng, replace: bool = False) -> dict:
    """Pull every source into bundle/ and write the manifest. Returns the manifest."""
    srcs = sources(eng.config)
    if not srcs:
        raise AuditError("engagement.yaml names no source. Add `source:` or `sources:` (see references/engagement-folder.md).")
    previous = None
    if eng.bundle.exists():
        if not replace:
            raise AuditError("bundle/ already exists. Evidence is collected once per engagement; use --replace to pull again "
                             "(the old bundle is kept as bundle.replaced-<timestamp>).")
        if eng.manifest_path.exists():
            previous = json.loads(eng.manifest_path.read_text(encoding="utf-8"))
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.move(str(eng.bundle), str(eng.root / f"bundle.replaced-{stamp}"))
    writer = BundleWriter(eng.bundle, "+".join(s["connector"] for s in srcs), framework=eng.framework)
    if previous:
        writer.keep_ids_from(previous)
    labels = []
    for src in srcs:
        writer.source = ""
        connectors.load(src["connector"]).pull(writer, src.get("options") or {}, eng)
        labels.append(f"{src['connector']}: {writer.source}" if len(srcs) > 1 and writer.source else writer.source)
    writer.source = "; ".join(x for x in labels if x)
    if not any(a["id"] == "SY-controls" for a in writer.artifacts):
        writer.warn("no source provided a control matrix; every requirement in scope is assessed directly")
        writer.set_controls([])
    return writer.finish()
