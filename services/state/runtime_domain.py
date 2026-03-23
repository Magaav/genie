#!/usr/bin/env python3

from __future__ import annotations

from common import STATE_LAYOUT, directory_summary


def summary() -> dict:
    runtime_dir = STATE_LAYOUT["runtime_dir"]
    return {
        "domain": "runtime",
        "dir": str(runtime_dir),
        "packages": directory_summary(STATE_LAYOUT["runtime_packages_dir"], recent_limit=3),
        "responses": directory_summary(STATE_LAYOUT["runtime_responses_dir"], recent_limit=3),
        "bridge": directory_summary(STATE_LAYOUT["runtime_bridge_dir"], recent_limit=3),
        "frontier": directory_summary(STATE_LAYOUT["runtime_frontier_dir"], recent_limit=3),
    }
