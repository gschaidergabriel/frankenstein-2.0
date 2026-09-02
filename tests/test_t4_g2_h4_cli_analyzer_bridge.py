#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "research/local_voice/tools/t7_pipewire_g2_h4_guard_cli.py"


class Trigger4G2H4CliAnalyzerBridgeTests(unittest.TestCase):
    def test_dynamic_harness_style_import_exposes_pcm_helpers(self) -> None:
        """Mirror the G2 harness' spec_from_file_location import path."""
        module_name = "test_t4_g2_h4_cli_dynamic_bridge"
        spec = importlib.util.spec_from_file_location(module_name, CLI)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            self.assertTrue(callable(module.main))
            self.assertTrue(callable(module.load_pcm16_wav))
            self.assertTrue(callable(module.fft_alignment_offset))
            self.assertTrue(callable(module.scan_correlated_windows))
        finally:
            sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
