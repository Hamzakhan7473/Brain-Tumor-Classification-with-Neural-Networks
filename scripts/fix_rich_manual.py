#!/usr/bin/env python3
"""
Fix broken 'rich' installs (no RECORD file / can't uninstall).

This script removes:
  - site-packages/rich/
  - any rich-*.dist-info or rich*.egg-info metadata directories

Then installs rich with --ignore-installed so pip does not try to uninstall
the broken "rich None" entry (which would fail).
"""

import subprocess
import sys
import shutil
from pathlib import Path


def _site_packages_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        import sysconfig
        dirs.append(Path(sysconfig.get_paths()["purelib"]))
    except Exception:
        pass
    try:
        import site
        for p in site.getsitepackages():
            dirs.append(Path(p))
    except Exception:
        pass
    seen = set()
    out = []
    for d in dirs:
        if str(d) not in seen:
            seen.add(str(d))
            out.append(d)
    return out


def _safe_rmtree(p: Path) -> bool:
    """Remove path. Returns True if removed, False on permission error."""
    if not p.exists():
        return True
    try:
        if p.is_symlink() or p.is_file():
            p.unlink()
            return True
        shutil.rmtree(p)
        return True
    except PermissionError:
        print("  Permission denied (run Terminal without sandbox or use sudo).", file=sys.stderr)
        return False


def main():
    sp_dirs = [d for d in _site_packages_dirs() if d.exists()]
    if not sp_dirs:
        print("Could not locate site-packages.", file=sys.stderr)
        return 1

    removed_any = False
    for sp in sp_dirs:
        rich_pkg = sp / "rich"
        if rich_pkg.exists():
            print("Removing:", rich_pkg)
            if _safe_rmtree(rich_pkg):
                removed_any = True

        for meta in list(sp.glob("rich-*.dist-info")) + list(sp.glob("rich*.egg-info")):
            print("Removing:", meta)
            if _safe_rmtree(meta):
                removed_any = True

    if not removed_any:
        print("No rich files found to remove (or removal was skipped due to permissions).")
        print("If you see 'Permission denied' above, run in your Terminal (outside Cursor):")
        print("  SITE=$(python -c 'import site; print(site.getsitepackages()[0])')")
        print("  rm -rf \"$SITE/rich\" \"$SITE\"/rich-*.dist-info")
        print("Then run this script again.")

    # Install rich without touching pip's broken "rich None" record
    print("\nInstalling rich with --ignore-installed ...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--ignore-installed", "rich"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("pip install failed:", r.stderr or r.stdout, file=sys.stderr)
        print("\nRun manually: python -m pip install --ignore-installed rich")
        return 1
    print("  OK")

    # Verify
    try:
        import rich
        ver = getattr(rich, "__version__", "?")
        print("  import rich:", "OK", f"(version {ver})")
    except Exception as e:
        print("  import rich: FAIL", e, file=sys.stderr)
        return 1

    print("\nAll set. Try: python -c \"from tensorflow import keras; print('keras OK')\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
