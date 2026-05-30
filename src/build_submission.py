"""Build the Kaggle submission tarball from the canonical src/ agent.

The Orbit Wars agent is multi-file (main.py imports geometry.py + prediction.py),
so the submission must be a tar.gz with all three files at the archive root.

    python -m build_submission                 # writes ./submission.tar.gz
    python -m build_submission --out foo.tar.gz

Then submit with:
    kaggle competitions submit orbit-wars -f submission.tar.gz -m "solution A v3"
"""

from __future__ import annotations

import argparse
import os
import tarfile
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent
AGENT_FILES = ["main.py", "geometry.py", "prediction.py"]


def build(out_path: Path) -> Path:
    for name in AGENT_FILES:
        if not (SRC_DIR / name).exists():
            raise FileNotFoundError(f"missing agent file: {SRC_DIR / name}")
    with tarfile.open(out_path, "w:gz") as tar:
        for name in AGENT_FILES:
            # arcname without directory -> files land at the archive root.
            tar.add(SRC_DIR / name, arcname=name)
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "submission.tar.gz")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = build(args.out)
    size = os.path.getsize(out)
    print(f"Built {out} ({size} bytes) with: {', '.join(AGENT_FILES)}")


if __name__ == "__main__":
    main()
