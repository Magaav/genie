#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path


CONSTITUTION_PATH = Path("/local/CONSTITUTION.md")


class ConstitutionTests(unittest.TestCase):
    def test_constitution_kernel_contains_core_limits(self) -> None:
        text = CONSTITUTION_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("never cross hard limits", text)
        self.assertIn("severe suffering", text)
        self.assertIn("unjustified coercion", text)
        self.assertIn("catastrophic risk", text)
        self.assertIn("manipulation", text)
        self.assertIn("dependency", text)
        self.assertIn("self-determination", text)


if __name__ == "__main__":
    unittest.main()
