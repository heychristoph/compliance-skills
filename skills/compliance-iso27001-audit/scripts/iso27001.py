#!/usr/bin/env python3
"""iso27001.py: the deterministic half of an AI Audit against ISO/IEC 27001:2022.

The report is an AI Audit. It is not an ISO/IEC 27001 certification audit.
The commands live in the shared requirements engine (scripts/engine/); this skill's
assets/profile.yaml makes it an ISO/IEC 27001 audit. Run `iso27001.py --help`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "engine"), str(HERE)]

from cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
