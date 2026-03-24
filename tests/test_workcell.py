#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SUPPORT_PATH = Path("/local/services/ethics/workcell_support.py")
ETHICS_DIR = Path("/local/services/ethics")
if str(ETHICS_DIR) not in sys.path:
    sys.path.insert(0, str(ETHICS_DIR))
SPEC = importlib.util.spec_from_file_location("genie_workcell_support", SUPPORT_PATH)
SUPPORT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SUPPORT
SPEC.loader.exec_module(SUPPORT)

ETHICS_PATH = Path("/local/services/ethics/app.py")
ETHICS_SPEC = importlib.util.spec_from_file_location("genie_ethics_app", ETHICS_PATH)
ETHICS = importlib.util.module_from_spec(ETHICS_SPEC)
assert ETHICS_SPEC.loader is not None
sys.modules[ETHICS_SPEC.name] = ETHICS
ETHICS_SPEC.loader.exec_module(ETHICS)


class WorkcellSupportTests(unittest.TestCase):
    def test_infers_docs_scope(self) -> None:
        self.assertEqual(SUPPORT.infer_workcell_scope("update the README with router details"), "docs")

    def test_infers_tests_scope(self) -> None:
        self.assertEqual(SUPPORT.infer_workcell_scope("add tests for instinct denial"), "tests")

    def test_extracts_fenced_python(self) -> None:
        payload = "```python\nprint('ok')\n```"
        self.assertEqual(SUPPORT.extract_fenced_content(payload, preferred_language="python"), "print('ok')")

    def test_parses_critique_report(self) -> None:
        parsed = SUPPORT.parse_critique_report(
            "APPROVED: yes\nSAFE_AUTO_APPLY: no\nSUMMARY: needs review\nISSUES:\n- add more assertions\n"
        )
        self.assertTrue(parsed["approved"])
        self.assertFalse(parsed["safe_auto_apply"])
        self.assertEqual(parsed["summary"], "needs review")
        self.assertEqual(parsed["issues"], ["add more assertions"])

    def test_detects_stale_processing_record(self) -> None:
        record = {
            "status": "processing",
            "operator_confirmed": True,
            "updated_at": "2000-01-01T00:00:00+00:00",
        }
        self.assertTrue(ETHICS.is_stale_processing_record(record))
        self.assertTrue(ETHICS.is_runnable_workcell_record(record))


if __name__ == "__main__":
    unittest.main()
