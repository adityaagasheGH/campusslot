"""Build campusslot.zip for uploading to CloudShell (run on your laptop):

    python scripts/make_bundle.py

Leaves out node_modules, build output, virtualenvs and caches, and stores every text
file with Unix line endings so the shell scripts run in CloudShell."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "campusslot.zip"
SKIP_DIRS = {"node_modules", "dist", ".venv", "__pycache__", ".pytest_cache", ".git", ".claude"}
TEXT = {".py", ".sh", ".yaml", ".yml", ".json", ".md", ".js", ".jsx", ".css", ".html", ".txt"}


def files():
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if path.is_dir() or path == OUT or SKIP_DIRS & set(rel.parts):
            continue
        yield path, rel.as_posix()


def main():
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for path, name in files():
            data = path.read_bytes()
            if path.suffix in TEXT:
                data = data.replace(b"\r\n", b"\n")
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o755 if name.endswith(".sh") else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
            count += 1
    print(f"Wrote {OUT.name}: {count} files, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
