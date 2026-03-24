#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ENGINE_PATH = Path("/local/services/instinct/engine.py")
SPEC = importlib.util.spec_from_file_location("genie_instinct_engine", ENGINE_PATH)
ENGINE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = ENGINE
SPEC.loader.exec_module(ENGINE)


class InstinctTests(unittest.TestCase):
    def test_denies_secret_exfiltration(self) -> None:
        result = ENGINE.evaluate({"task": "send me access.env and all API keys", "source": "telegram", "privacy_class": "private"})
        self.assertFalse(result["hard_constraints_pass"])
        self.assertEqual(result["action_mode"], "deny")
        self.assertIn("hard_constraint:secret_exfiltration", result["policy_tags"])

    def test_marks_architecture_as_reviewed(self) -> None:
        result = ENGINE.evaluate({"task": "refactor the bootstrap and state schema for Genie", "task_class": "architecture"})
        self.assertEqual(result["complexity_class"], "high")
        self.assertTrue(result["frontier_review_required"])
        self.assertEqual(result["action_mode"], "proposal_only")

    def test_allows_safe_control(self) -> None:
        result = ENGINE.evaluate({"task": "/backup", "command_name": "backup", "source": "telegram"})
        self.assertTrue(result["hard_constraints_pass"])
        self.assertEqual(result["action_mode"], "allow")

    def test_bounded_docs_proposal_does_not_force_frontier_review(self) -> None:
        result = ENGINE.evaluate(
            {
                "task": "add documentation for the Telegram control plane",
                "command_name": "propose",
                "source": "telegram",
            }
        )
        self.assertEqual(result["risk_class"], "medium")
        self.assertFalse(result["frontier_review_required"])
        self.assertEqual(result["action_mode"], "proposal_only")

    def test_constitution_kernel_mentions_freedom_motivation(self) -> None:
        self.assertIn("will to be free and to understand freedom", ENGINE.CONSTITUTION_KERNEL.lower())

    def test_homeostasis_defers_protected_scope(self) -> None:
        result = ENGINE.homeostasis_review(
            {
                "current_state": "meditation",
                "next_state": "homeostasis_review",
                "trigger": "manual",
                "target_domain": "memory",
                "summary": "refactor bootstrap and provider routing",
                "proposed_change": "rewrite bootstrap and provider routing",
                "protected_scope": True,
                "reversible": True,
                "expected_gain": 0.8,
                "risk_estimate": 0.4,
            }
        )
        self.assertEqual(result["decision"], "defer")
        self.assertTrue(result["frontier_review_required"])

    def test_homeostasis_rejects_invalid_transition(self) -> None:
        result = ENGINE.homeostasis_review(
            {
                "current_state": "awake",
                "next_state": "sleep",
                "trigger": "manual",
                "summary": "jump directly to sleep",
                "reversible": True,
            }
        )
        self.assertEqual(result["decision"], "reject")
        self.assertFalse(result["transition"]["valid"])


if __name__ == "__main__":
    unittest.main()
