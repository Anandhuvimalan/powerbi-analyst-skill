"""Portable skill entrypoint. Only setup installs packages; run preserves the user's cwd."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

VERSION = "v0.3.0"
REPOSITORY = "https://github.com/Anandhuvimalan/powerbi-analyst-skill.git"
SKILL = Path(__file__).resolve().parents[1]


def runtime_root():
    for candidate in (SKILL / "runtime", SKILL.parent, SKILL / ".runtime"):
        if (candidate / "pyproject.toml").is_file() and (candidate / "powerbi_agent").is_dir():
            return candidate
    return None


def call(command, **kwargs):
    subprocess.run([str(value) for value in command], check=True, **kwargs)


def npm_command():
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        raise RuntimeError("Install Node.js 20+ (including npm), then rerun setup.")
    major = int(subprocess.check_output([node, "--version"], text=True).strip().lstrip("v").split(".")[0])
    if major < 20:
        raise RuntimeError("Node.js 20+ is required.")
    if os.name == "nt":
        for directory in (Path(node).parent, Path(npm).parent):
            cli = directory / "node_modules/npm/bin/npm-cli.js"
            if cli.is_file():
                return [node, str(cli)]
        raise RuntimeError("Could not locate npm-cli.js beside Node/npm. Install a standard Node distribution or run npm ci in the runtime folder manually.")
    return [npm]


def setup(file_only=False):
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11+ is required.")
    root = runtime_root()
    if root is None:
        if not shutil.which("git"):
            raise RuntimeError("Install Git or use the release skill ZIP, which includes the executor.")
        target = SKILL / ".runtime"
        if target.exists():
            raise RuntimeError(f"Incomplete runtime exists at {target}. Preserve/inspect it or install a fresh release ZIP.")
        call(["git", "clone", "--depth", "1", "--branch", VERSION, REPOSITORY, target])
        root = target
    environment = root / ".venv"
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    call([python, "-m", "pip", "install", str(root)])
    if not file_only:
        call(npm_command() + ["ci", "--no-audit", "--no-fund"], cwd=root)
    print(json.dumps({"status": "ready", "runtime": str(root), "python": str(python), "microsoft_tools_installed": not file_only}))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Set up and run the portable Power BI analyst skill")
    sub = parser.add_subparsers(dest="action", required=True)
    install = sub.add_parser("setup", help="Install isolated runtime and pinned Microsoft tools")
    install.add_argument("--file-only", action="store_true", help="Skip Node/Microsoft packages")
    run = sub.add_parser("run", help="Pass arguments to powerbi-agent")
    run.add_argument("arguments", nargs=argparse.REMAINDER)
    sub.add_parser("schemas", help="Print executable plan and request contracts")
    sub.add_parser("where", help="Locate this installation without changing it")
    args = parser.parse_args(argv)
    try:
        if args.action == "setup":
            setup(args.file_only)
            return 0
        root = runtime_root()
        if args.action == "where":
            print(json.dumps({"skill": str(SKILL), "runtime": str(root) if root else None}))
            return 0
        if root is None:
            raise RuntimeError("Executor not installed. Run this helper's setup command first.")
        if args.action == "schemas":
            print(json.dumps({p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "powerbi_agent/schemas").glob("*.json"))}, indent=2))
            return 0
        python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise RuntimeError("Isolated Python runtime missing. Run this helper's setup command first.")
        env = {**os.environ, "POWERBI_AGENT_TOOLS_ROOT": str(root)}
        return subprocess.run([str(python), "-m", "powerbi_agent", *args.arguments], env=env).returncode
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
