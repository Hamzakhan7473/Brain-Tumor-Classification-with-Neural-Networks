#!/usr/bin/env python3
"""
Fix TensorFlow + protobuf environment (runtime_version ImportError).

TensorFlow does not work with protobuf 4.x. Use either:
  - protobuf 5.x (recommended), or
  - protobuf 3.20.x

Run from project root:
  pip install -r requirements.txt --upgrade
  # or:
  python scripts/fix_tensorflow_protobuf.py
"""
import subprocess
import sys


def main():
    print("Fixing TensorFlow + protobuf (resolve 'runtime_version' ImportError)...\n")

    # 1. Upgrade protobuf (TensorFlow is incompatible with 4.x; use 5.x or 3.20.x)
    print("1. Installing protobuf 5.x (TensorFlow incompatible with 4.x)...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "protobuf>=5.0,<6"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("   Trying protobuf 3.20.x instead...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "protobuf>=3.20,<4"],
            capture_output=True,
            text=True,
        )
    if r.returncode != 0:
        print("   stderr:", r.stderr)
        print("   Try manually: pip install --upgrade 'protobuf>=5.0,<6'")
    else:
        print("   OK")

    # 2. Reinstall TensorFlow so it picks up the new protobuf
    print("\n2. Reinstalling TensorFlow...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", "tensorflow"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        if "rich" in (r.stderr or "") and ("RECORD" in (r.stderr or "") or "uninstall" in (r.stderr or "")):
            print("   Fixing broken 'rich' package (no RECORD file)...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", "rich"],
                capture_output=True,
                text=True,
            )
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", "tensorflow"],
                capture_output=True,
                text=True,
            )
        if r.returncode != 0:
            print("   stderr:", r.stderr)
            print("   Try: pip install --force-reinstall --no-deps rich")
            print("   then: pip install --upgrade --force-reinstall tensorflow")
            return 1
    print("   OK")

    # 3. Fix numpy/pandas binary compatibility (dtype size changed - often pandas built against old numpy)
    print("\n3. Reinstalling numpy and pandas for binary compatibility...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", "numpy", "pandas"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print("   stderr:", r.stderr)
    print("   OK")

    # 4. Verify
    print("\n4. Verifying import...")
    try:
        from tensorflow import keras
        print("   tensorflow.keras imported successfully.")
    except Exception as e:
        err = str(e)
        if "numpy.dtype size changed" in err or "binary incompatibility" in err or "Expected 96" in err:
            print("   FAIL: numpy/pandas ABI mismatch (pandas was built against different numpy).")
            print("   Run:")
            print("      pip install --upgrade --force-reinstall numpy pandas")
            print("   then: python -c \"from tensorflow import keras; print('OK')\"")
        else:
            print("   FAIL:", e)
        return 1

    print("\nDone. You can now run training and use model predictions in the app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
