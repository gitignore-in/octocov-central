#!/usr/bin/env python3
"""Regression tests for check-octocov-source-artifacts.py."""

import importlib.util
import sys
from pathlib import Path


def load_module():
    module_path = Path(__file__).with_name("check-octocov-source-artifacts.py")
    spec = importlib.util.spec_from_file_location(
        "check_octocov_source_artifacts",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_select_latest_artifact_prefers_default_branch() -> None:
    module = load_module()
    artifacts = [
        {
            "id": 10,
            "name": "octocov-report",
            "expired": False,
            "created_at": "2026-07-01T10:00:00Z",
            "workflow_run": {"head_branch": "feature/refactor"},
        },
        {
            "id": 11,
            "name": "octocov-report",
            "expired": False,
            "created_at": "2026-07-01T09:59:59Z",
            "workflow_run": {"head_branch": "main"},
        },
        {
            "id": 12,
            "name": "octocov-report",
            "expired": False,
            "created_at": "2026-07-01T10:05:00Z",
            "workflow_run": {"head_branch": "main"},
        },
    ]

    selected = module.select_latest_artifact(artifacts, "main")

    assert selected is not None
    assert selected["id"] == 12


def test_select_latest_artifact_returns_none_without_default_branch_match() -> None:
    module = load_module()
    artifacts = [
        {
            "id": 21,
            "name": "octocov-report",
            "expired": False,
            "created_at": "2026-07-01T10:00:00Z",
            "workflow_run": {"head_branch": "feature/refactor"},
        },
        {
            "id": 22,
            "name": "octocov-report",
            "expired": False,
            "created_at": "2026-07-01T10:10:00Z",
            "workflow_run": {"head_branch": "release"},
        },
    ]

    assert module.select_latest_artifact(artifacts, "main") is None


def main() -> int:
    test_select_latest_artifact_prefers_default_branch()
    test_select_latest_artifact_returns_none_without_default_branch_match()
    print("OK: check-octocov-source-artifacts selection tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
