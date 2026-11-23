# Copied from shared/lib/capture.py by tools/sync.py. Edit that file, not this copy.
"""`capture`: record evidence the agent gathered itself, so it can be hashed and cited like any other.

Not every system has a connector. The agent can still get evidence:

  --via mcp     the raw response of an MCP tool call (Supabase advisors, a GitHub API read)
  --via cli     the output of a read-only command, run by this script so the output is untouched
  --via export  a file or screenshot the user provided (a settings page, a signed contract)
  --via answer  the user's answer to a question, when nothing can be checked

Each capture is written once to `intake/` in the engagement: the payload plus a
`.meta.json` sidecar saying how it was obtained. Nothing in intake/ is overwritten.
The `intake` connector turns it into bundle artifacts with the matching evidence
tier: direct pulls are strongest, then captured (mcp, cli), then client (export),
then inquiry (answer).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from .bundle import slug
from .io import AuditError, now_utc

INTAKE = "intake"
TIERS = {"mcp": "captured", "cli": "captured", "export": "client", "answer": "inquiry", "scan": "direct", "probe": "direct"}
CLI_ROUTES = ("mcp", "cli", "export", "answer")  # `scan` is written by detect, not by hand

# A CLI capture must only read. These words anywhere in the command mean it might change something.
MUTATING = re.compile(
    r"(?<![\w-])(delete|drop|remove|rm|rmdir|mv|update|insert|create|deploy|push|apply|reset|write|set|put|post|patch|"
    r"migrate|migration|truncate|alter|grant|revoke|destroy|kill|restart|stop|start|link|login|logout|init|install|"
    r"uninstall|upgrade|exec|ssh|scp|rotate|revoke|disable|enable|merge|commit|tag|release|publish|upload)(?![\w-])",
    re.I,
)
SHELL_META = re.compile(r"[;&|`$<>]|\$\(")
CLI_TIMEOUT = 120


def capture(root: Path, *, via: str, title: str, payload: bytes | None = None, file: Path | None = None,
            command: list[str] | None = None, server: str = "", tool: str = "", args=None, requirements=(),
            controls=(), recipe: str = "", request: str = "", question: str = "", by: str = "", ext: str = "",
            cwd: Path | None = None) -> Path:
    """Write one capture to <root>/intake/ and return the payload path."""
    if via not in TIERS:
        raise AuditError(f"--via must be one of {', '.join(TIERS)}")
    if not title.strip():
        raise AuditError("--title is required: what this evidence shows, as a tester would cite it")
    meta = {"via": via, "title": title.strip(), "at": now_utc(), "by": by, "requirements": list(dict.fromkeys(requirements)),
            "controls": list(dict.fromkeys(controls)), "recipe": recipe, "request": request}
    if via in ("scan", "probe"):
        payload = _payload(payload, file)
        ext = ext or ".json"
    elif via == "mcp":
        if not (server and tool):
            raise AuditError("--via mcp needs --server and --tool (and --args when the call had arguments)")
        meta.update(server=server, tool=tool, args=args or {})
        payload = _payload(payload, file)
        ext = ext or ".json"
    elif via == "cli":
        if not command:
            raise AuditError("--via cli needs the command after `--`, e.g. capture <dir> --via cli --title ... -- supabase projects list")
        payload, meta["command"], meta["exit_code"] = _run(command, cwd)
        if cwd:
            meta["cwd"] = str(cwd)
        ext = ext or ".txt"
    elif via == "export":
        if not file:
            raise AuditError("--via export needs --file: the export or screenshot the user provided")
        payload = Path(file).read_bytes()
        ext = ext or Path(file).suffix or ".bin"
        meta["original_name"] = Path(file).name
    else:  # answer
        if not question.strip():
            raise AuditError("--via answer needs --question (as asked) and the answer as --text, --file or stdin")
        meta["question"] = question.strip()
        answer = _payload(payload, file).decode("utf-8", errors="replace").strip()
        if not answer:
            raise AuditError("the answer is empty")
        payload = f"Question: {question.strip()}\n\nAnswer: {answer}\n\nAnswered by: {by or 'not recorded'}\n".encode()
        ext = ".md"
    intake = Path(root) / INTAKE
    intake.mkdir(parents=True, exist_ok=True)
    n = 1 + max([int(p.name[:4]) for p in intake.glob("[0-9][0-9][0-9][0-9]-*.meta.json")] or [0])
    stem = f"{n:04d}-{via}-{slug(title)[:40]}"
    path = intake / f"{stem}{ext}"
    path.write_bytes(payload)
    (intake / f"{stem}.meta.json").write_text(json.dumps({**meta, "file": path.name}, indent=2, ensure_ascii=False) + "\n")
    return path


def entries(root: Path) -> list[tuple[Path, dict]]:
    """Every capture in intake/, oldest first."""
    intake = Path(root) / INTAKE
    out = []
    for meta_path in sorted(intake.glob("[0-9][0-9][0-9][0-9]-*.meta.json")) if intake.is_dir() else []:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        out.append((intake / meta["file"], meta))
    return out


# Read-only command forms capture may run: program -> the subcommand prefixes allowed. Anything
# else is refused (fail closed): interpreters, scripts and unknown tools can write whatever their
# arguments look like. To add a tool, add its read-only forms here, never a whole program.
READ_ONLY = {
    # Only commands that read committed history: anything that compares against the working tree (status,
    # diff, blame) can run the repository's own clean/textconv filter programs.
    "git": [["log"], ["show"], ["ls-files"], ["rev-parse"], ["describe"], ["shortlog"]],
    "gh": [["api"], ["repo", "view"], ["pr", "list"], ["pr", "view"], ["run", "list"], ["run", "view"], ["secret", "list"],
           ["ruleset", "list"], ["ruleset", "view"], ["api", "--paginate"]],
    "supabase": [["projects", "list"], ["db", "dump"], ["inspect"], ["functions", "list"], ["secrets", "list"], ["branches", "list"]],
    # npm only: yarn and pnpm can load executables and hooks from the repository (yarnPath, .pnpmfile.cjs).
    "npm": [["audit"], ["ls"], ["outdated"]],
    "vercel": [["env", "ls"], ["project", "ls"], ["ls"], ["inspect"]],
    "netlify": [["status"], ["sites:list"]],
    "firebase": [["projects:list"], ["apps:list"]],
}


# Options that make an allowed command run a helper program or write a file. Refused anywhere in the command.
UNSAFE_OPTIONS = {
    "git": ("--ext-diff", "--textconv", "--output", "--exec", "--upload-pack", "--receive-pack", "-c", "--config-env",
            "--exec-path", "--git-dir", "--work-tree", "--open-files-in-pager", "-O"),
    "supabase": ("-f", "--file", "-o", "--output"),
    "npm": ("fix", "--fix"),
}
# Help and browser switches start viewers or browsers, some of them configurable by the repository.
HELP = {"--help", "-h", "help", "--man", "--web", "-w", "--info"}
# Git runs with helpers switched off, whatever the repository's own config says.
GIT_NO_VERIFIER = "/nonexistent/compliance-skills-capture-disabled"
GIT_SAFE = ["-c", "diff.external=", "-c", "core.pager=cat", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
            "-c", "pager.log=false", "-c", "pager.diff=false", "-c", "pager.show=false",
            # Signature verification runs a configurable program: never show or verify signatures.
            "-c", "log.showSignature=false", "-c", f"gpg.program={GIT_NO_VERIFIER}", "-c", f"gpg.openpgp.program={GIT_NO_VERIFIER}",
            "-c", f"gpg.ssh.program={GIT_NO_VERIFIER}", "-c", f"gpg.x509.program={GIT_NO_VERIFIER}", "--no-pager"]
GIT_NO_HELPERS = {"log": ["--no-ext-diff", "--no-textconv"], "show": ["--no-ext-diff", "--no-textconv"]}


def harden(command: list[str]) -> list[str]:
    """The command as capture runs it: git with external helpers, pagers and hooks disabled."""
    if Path(command[0]).name != "git" or len(command) < 2:
        return command
    sub = command[1]
    return [command[0], *GIT_SAFE, sub, *GIT_NO_HELPERS.get(sub, []), *command[2:]]


# gh api: only these options, so no combination can change the method or add a body (-X, -f, -F,
# --input, headers such as X-HTTP-Method-Override, or short-option clusters like -iXDELETE).
GH_API_FLAGS = {"--paginate", "--slurp", "-i", "--include", "--silent", "--verbose"}
GH_API_VALUED = {"--jq", "-q"}


def _check_gh_api(rest: list[str]) -> None:
    i = 0
    while i < len(rest):
        a = rest[i]
        if not a.startswith("-"):
            i += 1
            continue
        if a in GH_API_FLAGS:
            i += 1
        elif a in GH_API_VALUED:
            i += 2
        elif a.startswith("--jq="):
            i += 1
        else:
            raise AuditError(f"gh api option {a} is not allowed in a capture; allowed: {', '.join(sorted(GH_API_FLAGS | GH_API_VALUED))}")


def resolve_program(name: str, cwd: Path | None) -> str:
    """The trusted executable for a bare program name: found only in absolute PATH entries outside the
    assessed repository, never a path the caller supplies (`./git`) and never a relative PATH entry."""
    import shutil

    if os.sep in name or (os.altsep and os.altsep in name) or name in (".", ".."):
        raise AuditError(f"give the program by name ({Path(name).name}), not by path; capture runs the installed one")
    blocked = [Path(cwd).resolve()] if cwd else []  # the assessed repository; relative PATH entries are skipped below
    safe = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        resolved = Path(entry).resolve()
        if any(resolved == b or b in resolved.parents for b in blocked):
            continue
        safe.append(str(resolved))
    found = shutil.which(name, path=os.pathsep.join(safe))
    if not found:
        raise AuditError(f"{name} is not installed (or only found inside the assessed repository)")
    return found


def check_read_only(command: list[str]) -> None:
    if not command:
        raise AuditError("no command given")
    text = " ".join(command)
    if SHELL_META.search(text):
        raise AuditError("capture runs one command without a shell; remove pipes, redirects and substitutions")
    if os.sep in command[0] or (os.altsep and os.altsep in command[0]):
        raise AuditError(f"give the program by name ({Path(command[0]).name}), not by path; capture runs the installed one")
    program = command[0]
    forms = READ_ONLY.get(program)
    args = [a for a in command[1:] if not a.startswith("-")]
    # The allowed form must be the literal start of the command: no options before the subcommand,
    # because they can switch the program into another mode (`git --help log`).
    if not forms or not any(command[1:1 + len(f)] == f for f in forms):
        allowed = "; ".join(f"{p} {' '.join(f)}" for p, fs in READ_ONLY.items() for f in fs)
        raise AuditError(f"`{' '.join(command[:3])}` is not a known read-only command; capture only runs: {allowed}. "
                         "For anything else, run it yourself and capture the output as an export (`--via export --file`).")
    if HELP & set(command[1:]):
        raise AuditError("help and browser switches are not allowed in a capture")
    if program == "gh" and args[:1] == ["api"]:
        _check_gh_api(command[2:])
    unsafe = [a for a in command[1:] for o in UNSAFE_OPTIONS.get(program, ()) if a == o or a.startswith(o + "=")
              or (o.startswith("--") and a.startswith(o))]
    if program == "git":
        # Signature options and %G format placeholders make git run the signature verifier.
        unsafe += [a for a in command[1:] if a.startswith(("--show-signature", "--verify")) or "%G" in a]
    if unsafe:
        raise AuditError(f"{', '.join(sorted(set(unsafe)))} would run a helper program or write a file; not allowed in a capture")
    hit = MUTATING.search(" ".join(command[1:]))
    if hit and not (program == "gh" and args[:1] == ["api"]):
        raise AuditError(f"'{hit.group(0)}' could change the system; capture only runs read-only commands. "
                         "If this command only reads, capture its output as an export instead and say so in the title.")


def _run(command: list[str], cwd: Path | None = None) -> tuple[bytes, str, int]:
    check_read_only(command)
    try:
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_EXTERNAL_DIFF", "GIT_PAGER", "PAGER", "GIT_CONFIG_PARAMETERS")}
        run_cmd = harden(command)
        run_cmd[0] = resolve_program(command[0], cwd)
        out = subprocess.run(run_cmd, capture_output=True, timeout=CLI_TIMEOUT, cwd=str(cwd) if cwd else None,
                             env={**env, "GIT_PAGER": "cat", "PAGER": "cat", "GIT_TERMINAL_PROMPT": "0"})
    except FileNotFoundError as e:
        raise AuditError(f"{command[0]} is not installed or not on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise AuditError(f"{shlex.join(command)} did not finish in {CLI_TIMEOUT}s") from e
    body = out.stdout + (b"\n--- stderr ---\n" + out.stderr if out.stderr.strip() else b"")
    return body, shlex.join(command), out.returncode


def _payload(payload: bytes | None, file: Path | None) -> bytes:
    if payload is not None:
        return payload
    if file:
        return Path(file).read_bytes()
    if not sys.stdin.isatty():
        return sys.stdin.buffer.read()
    raise AuditError("give the content with --file, --text or on stdin")


# --- CLI -----------------------------------------------------------------------------


def add_parser(sub) -> None:
    """Register `capture` on an engine's command line."""
    s = sub.add_parser("capture", help="record evidence gathered via MCP, a read-only CLI command, an export or an answer")
    s.add_argument("engagement")
    s.add_argument("--via", required=True, choices=list(CLI_ROUTES))
    s.add_argument("--title", required=True, help="what this evidence shows")
    s.add_argument("--requirement", action="append", default=[], help="requirement ID it supports (repeatable)")
    s.add_argument("--control", action="append", default=[], help="control ID it supports (repeatable)")
    s.add_argument("--server", default="", help="MCP server (mcp)")
    s.add_argument("--tool", default="", help="MCP tool (mcp)")
    s.add_argument("--args", default="", help="MCP tool arguments as JSON (mcp)")
    s.add_argument("--file", help="payload file (mcp, export, answer); otherwise stdin")
    s.add_argument("--text", help="answer text (answer)")
    s.add_argument("--question", default="", help="the question as asked (answer)")
    s.add_argument("--recipe", default="", help="evidence recipe item this fulfils")
    s.add_argument("--request", default="", help="request ID from review/requests.csv this fulfils (export)")
    s.add_argument("--by", default="", help="who ran it or answered (agent and model, or the person's role)")
    s.add_argument("--cwd", help="directory to run a cli capture in (default: the engagement's repo, if detect recorded one)")
    s.add_argument("command", nargs="*", help="after --: the read-only command to run (cli)")
    s.set_defaults(fn=cmd_capture)


def cmd_capture(a) -> int:
    try:
        args = json.loads(a.args) if a.args else {}
    except json.JSONDecodeError as e:
        raise AuditError(f"--args is not valid JSON: {e}") from e
    cwd = Path(a.cwd) if a.cwd else None
    if cwd is None and a.via == "cli":
        cfg_path = Path(a.engagement) / "engagement.yaml"
        if cfg_path.exists():
            from .io import load_yaml

            repo = (load_yaml(cfg_path) or {}).get("repo")
            cwd = Path(repo) if repo and Path(repo).is_dir() else None
    path = capture(Path(a.engagement), cwd=cwd, via=a.via, title=a.title, file=Path(a.file) if a.file else None,
                   payload=a.text.encode() if a.text else None, command=a.command or None, server=a.server, tool=a.tool,
                   args=args, requirements=a.requirement, controls=a.control, recipe=a.recipe, request=a.request,
                   question=a.question, by=a.by)
    print(f"Captured {Path(a.engagement) / INTAKE / path.name} ({TIERS[a.via]} evidence). Run ingest --replace to add it to the bundle.")
    return 0
