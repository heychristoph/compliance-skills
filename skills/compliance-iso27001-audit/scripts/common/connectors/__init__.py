# Copied from shared/lib/connectors/__init__.py by tools/sync.py. Edit that file, not this copy.
"""Connectors turn a source system into an evidence bundle.

A connector is a module in this package with one function:

    def pull(writer: BundleWriter, options: dict, engagement) -> None

It reads from its source and calls `writer` to add controls, the description,
populations and evidence. `writer.framework` says which framework is audited:
its requirement IDs (`writer.find`), the description file, and whether there is a
Statement of Applicability. A connector never decides audit conclusions.

Shared by every audit skill. Add a connector by dropping a module here and a page
in each audit skill's references/connectors/; nothing else changes.
"""

import importlib
import pkgutil


def available() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_") and m.name != "base")


def load(name: str):
    if name not in available():
        from ..io import AuditError

        raise AuditError(f"Unknown connector '{name}'. Available: {', '.join(available())}.")
    return importlib.import_module(f"{__name__}.{name}")
