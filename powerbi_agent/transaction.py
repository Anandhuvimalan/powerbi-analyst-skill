"""Staged file transactions with independent Git checkpoints, backups and recovery."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

from .core import BuildError, identity, read_json, within, write_json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProjectTransaction:
    def __init__(self, project: Path):
        self.project = project.resolve()
        self.root = self.project.parent
        self.home = self.root / ".powerbi-agent" / identity(self.project.name)[:8]
        self.run = self.home / uuid.uuid4().hex[:8]
        self.stage = self.run / "s"
        self.manifest = self.home / "manifest.json"
        self.lock = self.root / ".powerbi-agent" / "project-write.lock"
        self.journal = self.home / "pending.json"
        self.old = {}
        self.acquired = False

    def __enter__(self):
        self.home.mkdir(parents=True, exist_ok=True)
        try:
            with self.lock.open("x") as stream:
                stream.write(str(os.getpid()))
            self.acquired = True
        except FileExistsError as exc:
            raise BuildError("Another build or interrupted transaction owns project-write.lock. Run powerbi-agent recover after confirming that process stopped.") from exc
        try:
            if self.journal.exists():
                raise BuildError("An interrupted publication requires powerbi-agent recover before building again.")
            if self.manifest.exists():
                self.old = read_json(self.manifest)["files"]
                for relative, expected in self.old.items():
                    path = within(self.root, relative)
                    if not path.is_file() or digest(path) != expected:
                        raise BuildError(f"Externally edited managed file: {relative}. Preserve/reconcile Desktop edits before rebuilding; no overwrite was made.")
            self.stage.mkdir(parents=True)
            return self
        except BaseException:
            self.lock.unlink(missing_ok=True)
            self.acquired = False
            raise

    def publish(self):
        for relative, expected in self.old.items():
            target = within(self.root, relative)
            if not target.is_file() or digest(target) != expected:
                raise BuildError(f"Managed file changed during the build: {relative}. Publication cancelled.")
        files = {p.relative_to(self.stage).as_posix(): digest(p) for p in self.stage.rglob("*") if p.is_file()}
        affected = sorted(set(files) | set(self.old))
        existing = [p for p in affected if within(self.root, p).is_file()]
        backup = self.run / "checkpoint.zip"
        with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as archive:
            for relative in existing:
                archive.write(within(self.root, relative), relative)
            if self.manifest.exists():
                archive.write(self.manifest, "_previous_manifest.json")
        # Separate Git repo: never stages, commits, resets or alters the user's index.
        checkpoint = self.run / "g"
        checkpoint.mkdir()
        for relative in existing:
            target = within(checkpoint, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(within(self.root, relative), target)
        git = shutil.which("git")
        if git:
            for args in [["init", "--quiet"], ["add", "--all"], ["-c", "user.name=Power BI Agent", "-c", "user.email=local@powerbi-agent.invalid", "commit", "--quiet", "--allow-empty", "-m", "Pre-build project checkpoint"]]:
                result = subprocess.run([git, "-C", str(checkpoint)] + args, capture_output=True, timeout=60)
                if result.returncode:
                    break  # ZIP remains the verified rollback source.
        journal = {"backup": str(backup), "affected": affected, "existing": existing, "run": str(self.run)}
        write_json(self.journal, journal)
        try:
            for relative in affected:
                target = within(self.root, relative)
                if relative in files:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name(target.name + ".agent-tmp")
                    shutil.copy2(within(self.stage, relative), temporary)
                    os.replace(temporary, target)
                else:
                    target.unlink(missing_ok=True)
            write_json(self.manifest, {"project": str(self.project), "files": files, "last_run": str(self.run)})
            self.journal.unlink()
        except BaseException:
            self.restore()
            raise
        return {"backup": str(backup), "files_written": len(files)}

    def restore(self):
        journal = read_json(self.journal)
        backup = Path(journal["backup"]).resolve()
        if not backup.is_relative_to(self.home.resolve()):
            raise BuildError("Recovery backup must be inside this project's transaction directory.")
        with zipfile.ZipFile(backup) as archive:
            for relative in journal["affected"]:
                target = within(self.root, relative)
                if relative in journal["existing"]:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(relative))
                else:
                    target.unlink(missing_ok=True)
                target.with_name(target.name + ".agent-tmp").unlink(missing_ok=True)
            if "_previous_manifest.json" in archive.namelist():
                self.manifest.write_bytes(archive.read("_previous_manifest.json"))
            else:
                self.manifest.unlink(missing_ok=True)
        self.journal.unlink()

    def __exit__(self, *args):
        if self.acquired:
            self.lock.unlink(missing_ok=True)


def recover(project: Path):
    tx = ProjectTransaction(project)
    if tx.lock.exists():
        try:
            pid = int(tx.lock.read_text())
            if os.name == "nt":
                import ctypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.restype = ctypes.c_void_p
                kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
                handle = kernel.OpenProcess(0x1000, 0, pid)
                if not handle:
                    if ctypes.get_last_error() == 87:
                        raise ProcessLookupError()
                    raise PermissionError()
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel.CloseHandle(handle)
            else:
                os.kill(pid, 0)
        except ProcessLookupError:
            pass
        except (ValueError, PermissionError, OSError) as exc:
            raise BuildError("Cannot prove the lock owner stopped; inspect project-write.lock manually.") from exc
        else:
            raise BuildError(f"Build process {pid} is still running; recovery refused.")
    if tx.journal.exists():
        tx.restore()
    tx.lock.unlink(missing_ok=True)
