#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


CONTROL_PATH = Path("/local/services/ethics/control_plane.py")
SPEC = importlib.util.spec_from_file_location("genie_control_plane", CONTROL_PATH)
CONTROL = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = CONTROL
SPEC.loader.exec_module(CONTROL)


class ControlPlaneTests(unittest.TestCase):
    def test_parse_propose_command(self) -> None:
        parsed = CONTROL.parse_control_command("/propose tighten backup restore flow")
        self.assertEqual(parsed["command"], "propose")
        self.assertEqual(parsed["argument"], "tighten backup restore flow")

    def test_parse_confirm_command(self) -> None:
        parsed = CONTROL.parse_control_command("/confirm proposal-000001")
        self.assertEqual(parsed["command"], "confirm")
        self.assertEqual(parsed["argument"], "proposal-000001")

    def test_non_command_returns_none(self) -> None:
        self.assertIsNone(CONTROL.parse_control_command("hello genie"))


if __name__ == "__main__":
    unittest.main()
