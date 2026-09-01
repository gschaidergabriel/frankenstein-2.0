#!/usr/bin/env python3
"""CLI entrypoint for the Trigger-7 G2 H4 evidence-validity guard."""
from __future__ import annotations

import sys

from t7_pipewire_g2_h4_guard import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
