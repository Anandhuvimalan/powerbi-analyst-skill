"""Build a portable skill from an explicit source allowlist, never local projects/data."""
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def members(root=ROOT):
    skill = root / "powerbi-analyst"
    files = {}
    for pattern in ("SKILL.md", "references/*.md", "agents/*.yaml", "scripts/*.py"):
        for path in skill.glob(pattern):
            files["powerbi-analyst/" + path.relative_to(skill).as_posix()] = path
    for path in (root / "powerbi_agent").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".json", ".ps1"} and "__pycache__" not in path.parts:
            files["powerbi-analyst/runtime/" + path.relative_to(root).as_posix()] = path
    for name in ("pyproject.toml", "package.json", "package-lock.json", "LICENSE"):
        files["powerbi-analyst/runtime/" + name] = root / name
    # setuptools installs the original knowledge beside the isolated interpreter.
    for path in [skill / "SKILL.md", *sorted((skill / "references").glob("*.md"))]:
        files["powerbi-analyst/runtime/powerbi-analyst/" + path.relative_to(skill).as_posix()] = path
    return files


def package(destination, root=ROOT):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name, path in sorted(members(root).items()):
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return hashlib.sha256(destination.read_bytes()).hexdigest()


if __name__ == "__main__":
    target = ROOT / "dist/powerbi-analyst.zip"
    digest = package(target)
    (target.parent / "SHA256SUMS.txt").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    print(f"Packaged {target} ({target.stat().st_size:,} bytes); SHA256 {digest}")
