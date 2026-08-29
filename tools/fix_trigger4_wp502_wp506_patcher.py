#!/usr/bin/env python3
"""Correct the one overly-specific test fixture matcher before the one-shot patch runs."""
from pathlib import Path

path = Path(__file__).with_name("trigger4_wp502_wp506_frame_version_patch.py")
text = path.read_text(encoding="utf-8")
old = '''replace_exact(\n    test_hyper,\n    \'\'\'        situation_frame_ref="situation:42",\\n        policy_ref="policy:bounded",\\n\'\'\',\n    \'\'\'        situation_frame_ref="situation:42",\\n        situation_frame_generation=4,\\n        situation_frame_sha256="a" * 64,\\n        policy_ref="policy:bounded",\\n\'\'\',\n    count=3,\n)'''
new = '''replace_exact(\n    test_hyper,\n    \'\'\'        situation_frame_ref="situation:42",\\n\'\'\',\n    \'\'\'        situation_frame_ref="situation:42",\\n        situation_frame_generation=4,\\n        situation_frame_sha256="a" * 64,\\n\'\'\',\n    count=3,\n)'''
if text.count(old) != 1:
    raise SystemExit(f"expected one matcher block, observed {text.count(old)}")
path.write_text(text.replace(old, new), encoding="utf-8")
print("corrected one-shot patcher fixture matcher")
