#!/usr/bin/env python3
"""Run the NIS2 audit skill on a fixture with any agent, then grade the result.

    python evals/nis2/run.py --case audit --agent oracle
    python evals/nis2/run.py --case assessment --agent oracle --language de
    python evals/nis2/run.py --case audit --agent 'claude -p --permission-mode bypassPermissions {prompt}'
    python evals/nis2/run.py --case audit --agent 'codex exec --full-auto {prompt}'

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
SKILL = HERE.parent.parent / "skills" / "compliance-nis2-audit"
sys.path.insert(0, str(HERE))

from graders import grade, print_grade  # noqa: E402

PROMPT = """You are running an AI Audit against the NIS 2 Directive (EU) 2022/2555 and Implementing Regulation (EU) 2024/2690 as a NIS2 {type}.
The engagement folder is {engagement}. Read {skill}/SKILL.md first and follow it.
Use `{python}` to run the skill's scripts; its dependencies are installed.
Sign the report with `nis2.py signoff --model` using the model name that did the work, then render.
The result is an AI Audit, not an audit by a competent authority and not legal advice. Do not ask questions."""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", default="audit", help="fixture name under evals/nis2/fixtures (audit, assessment)")
    p.add_argument("--agent", required=True, help="'oracle' or a command template containing {prompt}")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--language", choices=["en", "de"], help="report language for this run (default: the fixture's)")
    p.add_argument("--timeout", type=int, default=4 * 3600, help="seconds per run")
    a = p.parse_args()

    fixture = HERE / "fixtures" / a.case
    if not fixture.exists():
        sys.exit(f"No fixture {fixture}. Run: python evals/nis2/make_fixture.py")
    truth = json.loads((fixture / "truth.json").read_text())
    scores = []
    for i in range(a.runs):
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run = HERE / "runs" / f"{stamp}-{a.case}{'-' + a.language if a.language else ''}-{i + 1}"
        shutil.copytree(fixture, run, ignore=shutil.ignore_patterns("truth.json"))
        if a.language:
            _set_language(run, a.language, truth)
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


def _set_language(run: Path, lang: str, truth: dict) -> None:
    """Set `language` in the run's engagement.yaml. For a language the fixture is translated
    into, also use its scope statement and put its entity description at the engagement root,
    as the entity would provide them for a report in that language."""
    import yaml

    path = run / "engagement.yaml"
    cfg = yaml.safe_load(path.read_text())
    cfg["language"] = lang
    tr = (truth.get("translations") or {}).get(lang)
    if tr:
        cfg["scope"] = tr["scope"]
        (run / "context.yaml").write_text(yaml.safe_dump(tr["context"], sort_keys=False, allow_unicode=True))
    path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))


def _oracle(run: Path, truth_path: Path) -> None:
    nis2 = [sys.executable, str(SKILL / "scripts" / "nis2.py")]
    for step in ("ingest", "check", "plan"):
        r = subprocess.run(nis2 + [step, str(run)], stdout=subprocess.DEVNULL)
        if r.returncode not in (0, 1) or (step != "plan" and r.returncode):
            raise SystemExit(f"nis2.py {step} failed")
    subprocess.run([sys.executable, str(HERE / "oracle.py"), str(run), str(truth_path)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(nis2 + ["signoff", str(run), "--model", "oracle"], check=True, stdout=subprocess.DEVNULL)
    for step in ("render", "packet"):
        subprocess.run(nis2 + [step, str(run)], check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
