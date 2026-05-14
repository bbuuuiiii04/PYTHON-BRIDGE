#!/usr/bin/env python3
from pathlib import Path
import sys

REPO_DIR = Path(__file__).resolve().parents[1]
REPO_PARENT = REPO_DIR.parent
if str(REPO_PARENT) not in sys.path:
    sys.path.insert(0, str(REPO_PARENT))

from rb_ss_bridge_v2.tools.laser_pad_web import main


if __name__ == "__main__":
    raise SystemExit(main())
