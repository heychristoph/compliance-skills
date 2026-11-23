#!/usr/bin/env python3
"""gdpr.py: the deterministic half of an AI Audit against the GDPR (Regulation (EU) 2016/679).

The report is an AI Audit, not an official audit, a supervisory authority's decision or legal advice.
The commands live in the shared requirements engine (scripts/engine/); this skill's
assets/profile.yaml sets the framework. Run `gdpr.py --help`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / "engine"), str(HERE)]

from cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
