#!/usr/bin/env python3
"""Copy shared/ into every skill, so each skills/<name>/ folder stays self-contained.

Agent Skills are installed one folder at a time, and an agent can only read what is
inside that folder. Shared files live once in shared/ and are copied here:

    shared/frameworks/<name>.yaml        ->  skills/<skill>/assets/frameworks/<name>.yaml
    shared/frameworks/<lang>/<name>.yaml ->  skills/<skill>/assets/frameworks/<lang>/<name>.yaml
    shared/lib/*.py                      ->  skills/<skill>/scripts/common/*.py   (skills with scripts/)
    shared/engines/requirements/*        ->  skills/<skill>/scripts/engine/       (skills with assets/profile.yaml)

Edit shared/, then run `python tools/sync.py`. `--check` exits 1 when a copy is stale,
so tests and CI catch a forgotten sync. Never edit the copies.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "shared"
SKILLS = ROOT / "skills"

# (source folder under shared/, destination folder under each skill, only skills that have this folder)
TREES = [
    ("frameworks", "assets/frameworks", None),
    ("lib", "scripts/common", "scripts"),
    ("engines/requirements", "scripts/engine", "assets/profile.yaml"),  # ISO 27001, GDPR, NIS2 audits
]

HEADER = "# Copied from shared/{src} by tools/sync.py. Edit that file, not this copy.\n"
SKIP_DIRS = {"__pycache__"}


def skills(needs: str | None = None) -> list[Path]:
    return sorted(p.parent for p in SKILLS.glob("*/SKILL.md") if needs is None or (p.parent / needs).exists())


def expected() -> dict[Path, bytes]:
    """Every copy that should exist, with its exact content."""
    out = {}
    for src_dir, dest_dir, needs in TREES:
        for src in sorted((SHARED / src_dir).rglob("*")):
            if not src.is_file() or src.name.startswith(".") or SKIP_DIRS & set(src.parts) or src.suffix == ".pyc":
                continue
            rel = src.relative_to(SHARED / src_dir)
            body = src.read_bytes()
            if src.suffix in (".yaml", ".yml", ".py"):  # comment header; .json and .typ are copied as they are
                body = HEADER.format(src=f"{src_dir}/{rel.as_posix()}").encode() + body
            for skill in skills(needs):
                out[skill / dest_dir / rel] = body
    return out


def stale(want: dict[Path, bytes]) -> list[str]:
    problems = [f"stale or missing: {p.relative_to(ROOT)}" for p, body in want.items()
                if not p.exists() or p.read_bytes() != body]
    for _, dest_dir, _needs in TREES:
        for skill in skills():
            for p in (skill / dest_dir).rglob("*") if (skill / dest_dir).is_dir() else []:
                if p.is_file() and p not in want and not (SKIP_DIRS & set(p.parts)) and p.suffix != ".pyc":
                    problems.append(f"not in shared/: {p.relative_to(ROOT)}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report stale copies and exit 1; change nothing")
    args = ap.parse_args()
    want = expected()
    if args.check:
        problems = stale(want)
        for line in problems:
            print(line)
        if problems:
            print("Run: python tools/sync.py")
        return 1 if problems else 0
    for problem in stale(want):
        if problem.startswith("not in shared/: "):
            (ROOT / problem.removeprefix("not in shared/: ")).unlink()
    for path, body in want.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != body:
            path.write_bytes(body)
            print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
