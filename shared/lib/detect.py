"""`detect`: find out what an application is built with, and plan how to get evidence for it.

Stack knowledge is data: one recipe file per component (`assets/recipes/<component>.yaml`
in the skill) says how to recognize the component and, for each piece of evidence,
the ways to get it, best first:

  mcp       a read-only MCP tool call, if the agent has that server connected
  cli       a read-only command, if the tool is installed (run through `capture --via cli`)
  export    exact steps for the user to export a file or take a screenshot
  question  the catalog question, when nothing can be checked (evidence tier: inquiry)

`detect` scans the repository (codescan.py), matches recipes, records the scan as
evidence, and writes review/stack.yaml and review/evidence-plan.md. The agent then
works through the plan with whatever access it actually has.

Recipe format:

  component: supabase
  title: Supabase
  detect: {dependencies: [...], files: [...], text: [...]}   # any match detects it
  subprocessor: {name: Supabase, service: ..., dpa: <url>}   # listed in the sub-processor annex
  enables: [<optional requirement IDs that apply when the component is used>]
  items:
    - id: supabase-rls
      title: Row-level security on every table
      requirements: [SEC-AC-01]
      scan_rules: [supabase-service-role-key]     # codescan rules that are evidence for this item
      mcp: {server: supabase, tool: get_advisors, args: {type: security}, note: ...}
      cli: {command: [supabase, ...]}
      export: {en: "...", de: "..."}
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import codescan
from .io import load_yaml


def load_recipes(recipes_dir: Path) -> list[dict]:
    if not recipes_dir.is_dir():
        return []
    return [load_yaml(p) for p in sorted(recipes_dir.glob("*.yaml"))]


def detect(repo: Path, recipes: list[dict], scan: dict | None = None) -> tuple[list[dict], dict]:
    """Components the repository uses (recipes that match), and the code scan."""
    scan = scan if scan is not None else codescan.scan(repo)
    deps = set(scan["dependencies"])
    found = []
    for recipe in recipes:
        d = recipe.get("detect") or {}
        why = [f"dependency {x}" for x in d.get("dependencies") or [] if x in deps]
        why += [f"file {x}" for x in d.get("files") or [] if list(Path(repo).glob(x))]
        why += [f"mentions {x}" for x in d.get("text") or [] if _mentions(repo, x)]
        if d.get("always"):
            why.append("always assessed")
        if why:
            found.append({**recipe, "detected_by": why})
    return found, scan


def evidence_plan(components: list[dict], scan: dict, catalog: dict[str, dict], in_scope: set[str], lang: str = "en") -> list[dict]:
    """One row per evidence item of a detected component, for requirements in scope."""
    rows = []
    rules = {f["rule"] for f in scan["findings"]}
    for comp in components:
        for item in comp.get("items") or []:
            reqs = [r for r in item.get("requirements") or [] if r in in_scope]
            if not reqs:
                continue
            methods = []
            if item.get("scan_rules"):
                hits = sorted(rules & set(item["scan_rules"]))
                methods.append({"via": "scan", "detail": ("findings: " + ", ".join(hits)) if hits else "code scan found nothing for this item"})
            if item.get("probe"):
                methods.append({"via": "probe", "detail": f"probe {item['probe']} --authorized (ask the user first whether they may test the live system)"})
            if item.get("mcp"):
                m = item["mcp"]
                methods.append({"via": "mcp", "detail": f"{m['server']}.{m['tool']}({json.dumps(m.get('args') or {})})" + (f" — {m['note']}" if m.get("note") else "")})
            if item.get("cli"):
                methods.append({"via": "cli", "detail": " ".join(item["cli"]["command"])})
            if item.get("export"):
                exp = item["export"]
                methods.append({"via": "export", "detail": exp.get(lang) or exp.get("en")})
            question = (catalog.get(reqs[0]) or {}).get("question")
            if question:
                methods.append({"via": "answer", "detail": question})
            rows.append({"component": comp["component"], "item": item["id"], "title": item["title"], "requirements": reqs, "methods": methods})
    return rows


def write_plan(review_dir: Path, components: list[dict], scan: dict, rows: list[dict], uncovered: list[dict], prior: list[dict] | None = None) -> None:
    """review/stack.yaml (machine-readable) and review/evidence-plan.md (what the agent works through). Always English."""
    review_dir.mkdir(parents=True, exist_ok=True)
    stack = {
        "components": [{"component": c["component"], "title": c.get("title", c["component"]), "detected_by": c["detected_by"]} for c in components],
        "subprocessors": subprocessors(components, scan),
        "tables": scan["tables"], "buckets": scan["buckets"],
        "scan_findings": [{k: f[k] for k in ("rule", "severity", "file", "line")} for f in scan["findings"]],
    }
    (review_dir / "stack.yaml").write_text(yaml.safe_dump(stack, sort_keys=False, allow_unicode=True))
    lines = ["# Evidence plan", "",
             "Work through each item with the first method you can use. Capture every result with `capture` "
             "(`--recipe <item>` and the requirement IDs), then `ingest --replace`.", "",
             "- **mcp**: only if that MCP server is connected; connect it read-only and limited to this project. Never read table rows.",
             "- **cli**: only if the tool is installed and logged in; `capture --via cli -- <command>` runs it and refuses anything that writes.",
             "- **export**: collect every export request into one message to the user.",
             "- **answer**: ask only what nothing else could show; `capture --via answer`. Answers alone leave a requirement not verified.", "",
             "## Detected", ""]
    lines += [f"- **{c.get('title', c['component'])}**: {', '.join(c['detected_by'])}" for c in components] or ["- nothing recognized"]
    lines += ["", "## Items", ""]
    for r in rows:
        lines.append(f"### {r['item']}: {r['title']} ({', '.join(r['requirements'])})")
        lines += [f"{i}. **{m['via']}**: {m['detail']}" for i, m in enumerate(r["methods"], 1)]
        lines.append("")
    if prior:
        lines += ["## Evidence from the previous assessment", "",
                  "Ask the user once, for all of these together, whether each is still current. Re-capture the ones that are "
                  "(`capture --via export --file <file>` or `--via answer` with the same question) and gather the rest anew. "
                  "Configuration (mcp, cli, scan) is always captured again.", ""]
        lines += [f"- {p['at']} {p['via']}: {p['title']} ({', '.join(p['requirements'])}): `{p['file']}`" for p in prior]
        lines.append("")
    if uncovered:
        lines += ["## Requirements no recipe covers", "",
                  "Find evidence in the repository, the documentation or the records; otherwise ask the catalog question.", ""]
        lines += [f"- {r['id']} {r['title']}: {r.get('question', '')}" for r in uncovered]
    (review_dir / "evidence-plan.md").write_text("\n".join(lines) + "\n")


def subprocessors(components: list[dict], scan: dict) -> list[dict]:
    """Sub-processor candidates: recipes' declared services plus services the code calls."""
    out: dict[str, dict] = {}
    for c in components:
        sp = c.get("subprocessor")
        if sp:
            out[sp["name"]] = {"name": sp["name"], "service": sp.get("service", ""), "dpa": sp.get("dpa", ""), "found_by": f"recipe {c['component']}"}
    for s in scan["services"]:
        out.setdefault(s["name"], {"name": s["name"], "service": s["category"], "dpa": "", "found_by": "; ".join(s["evidence"][:2])})
    return sorted(out.values(), key=lambda s: s["name"])


def _mentions(repo: Path, needle: str) -> bool:
    for name in ("README.md", "index.html", "package.json", "vite.config.ts", "vite.config.js"):
        p = Path(repo) / name
        if p.exists() and needle.lower() in p.read_text(encoding="utf-8", errors="replace").lower():
            return True
    return False
