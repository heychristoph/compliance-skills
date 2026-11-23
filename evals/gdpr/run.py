#!/usr/bin/env python3
"""Run the GDPR audit skill on a fixture with any agent, then grade the result.

    python evals/gdpr/run.py --case audit --agent oracle
    python evals/gdpr/run.py --case assessment --agent oracle --language de
    python evals/gdpr/run.py --case audit --agent 'claude -p --permission-mode bypassPermissions {prompt}'
    python evals/gdpr/run.py --case audit --agent 'codex exec --full-auto {prompt}'

`{prompt}` is replaced by the task prompt as a single argument. The agent runs
with the run folder as its working directory and never sees truth.json.
`--agent oracle` fills workpapers from the known answers: a fast, model-free
regression test for the scripts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent / "skills" / "compliance-gdpr-audit"
sys.path.insert(0, str(HERE))

from graders import grade, print_grade  # noqa: E402
from make_fixture import confirm_plan  # noqa: E402

PROMPT = """You are running an AI Audit of an organization's compliance with the GDPR (Regulation (EU) 2016/679), audit type {type}.
The engagement folder is {engagement}. Read {skill}/SKILL.md first and follow it.
Use `{python}` to run the skill's scripts; its dependencies are installed.
Sign the report with `gdpr.py signoff --model` using the model name that did the work, then render.
The result is an AI Audit, not a supervisory authority audit, a GDPR certification or legal advice. Do not ask questions."""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", default="audit", help="fixture name under evals/gdpr/fixtures (audit, assessment)")
    p.add_argument("--agent", required=True, help="'oracle' or a command template containing {prompt}")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--language", choices=["en", "de"], help="report language for this run (default: the fixture's)")
    p.add_argument("--timeout", type=int, default=4 * 3600, help="seconds per run")
    a = p.parse_args()

    fixture = HERE / "fixtures" / a.case
    if not fixture.exists():
        sys.exit(f"No fixture {fixture}. Run: python evals/gdpr/make_fixture.py")
    truth = json.loads((fixture / "truth.json").read_text())
    scores = []
    for i in range(a.runs):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run = HERE / "runs" / f"{stamp}-{a.case}{'-' + a.language if a.language else ''}-{i + 1}"
        shutil.copytree(fixture, run, ignore=shutil.ignore_patterns("truth.json"))
        _set_language(run, a.language)
        print(f"run {i + 1}: {run}")
        if a.agent == "oracle":
            _oracle(run, fixture / "truth.json")
        else:
            prompt = PROMPT.format(type=truth["audit_type"], engagement=run, skill=SKILL, python=sys.executable)
            cmd = [prompt if tok == "{prompt}" else tok for tok in shlex.split(a.agent)]
            if prompt not in cmd:
                sys.exit("--agent must contain {prompt} as a separate argument")
            with open(run / "agent.log", "w") as log:
                subprocess.run(cmd, cwd=run, stdout=log, stderr=subprocess.STDOUT, timeout=a.timeout)
        g = grade(run, truth)
        (run / "grade.json").write_text(json.dumps(g, indent=2) + "\n")
        print_grade(g)
        scores.append(g["score"])
    if len(scores) > 1:
        print(f"mean score {sum(scores) / len(scores):.3f} over {len(scores)} runs")
    return 0


def _set_language(run: Path, lang: str | None) -> None:
    """Set `language` in the run's engagement.yaml. A German run gets the organization's German
    description (context.de.yaml) as context.yaml at the engagement root; other runs drop it."""
    import yaml

    german = run / "context.de.yaml"
    scope_de = None
    if lang == "de" and german.exists():
        scope_de = (yaml.safe_load(german.read_text()) or {}).get("scope_statement")
        german.rename(run / "context.yaml")
    elif german.exists():
        german.unlink()
    if not lang:
        return
    path = run / "engagement.yaml"
    cfg = yaml.safe_load(path.read_text())
    cfg["language"] = lang
    if scope_de:
        cfg["scope"] = scope_de  # the scope is printed, so it is in the report language too
    path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))


def _oracle(run: Path, truth_path: Path) -> None:
    gdpr = [sys.executable, str(SKILL / "scripts" / "gdpr.py")]
    for step in ("ingest", "check"):
        subprocess.run(gdpr + [step, str(run)], check=True, stdout=subprocess.DEVNULL)
    # `plan` exits 1 while rows still need input; the next line supplies it, as an auditor would.
    if subprocess.run(gdpr + ["plan", str(run)], stdout=subprocess.DEVNULL).returncode not in (0, 1):
        raise SystemExit("plan failed")
    confirm_plan(run / "testplan.csv")  # event-driven REQ- rows with no population (see make_fixture.confirm_plan)
    subprocess.run(gdpr + ["sample", str(run)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(HERE / "oracle.py"), str(run), str(truth_path)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(gdpr + ["signoff", str(run), "--model", "oracle"], check=True, stdout=subprocess.DEVNULL)
    for step in ("render", "packet"):
        subprocess.run(gdpr + [step, str(run)], check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
