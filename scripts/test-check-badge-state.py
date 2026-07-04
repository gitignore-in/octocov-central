#!/usr/bin/env python3
"""Regression tests for check-badge-state.py."""

import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def load_module():
    module_path = Path(__file__).with_name("check-badge-state.py")
    spec = importlib.util.spec_from_file_location("check_badge_state", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_datastore_repos_ignores_inactive_artifact_uris() -> None:
    module = load_module()
    with TemporaryDirectory() as tmpdir:
        octocov_path = Path(tmpdir) / ".octocov.yml"
        octocov_path.write_text(
            """\
# Trust boundary: comments may include retired artifact URIs.
central:
  reports:
    datastores:
      - artifact://gitignore-in/gitignore-in/octocov-report
      # Removed 2026-05-01: repo archived.
      # - artifact://gitignore-in/old-repo/octocov-report
      - "artifact://gitignore-in/website/octocov-report" # active
  badges:
    datastores:
      - local://badges
      # - artifact://gitignore-in/not-a-report/octocov-report
outside:
  - artifact://gitignore-in/not-central/octocov-report
""",
            encoding="utf-8",
        )

        assert module.parse_datastore_repos(octocov_path) == {
            "gitignore-in/gitignore-in",
            "gitignore-in/website",
        }


def main() -> int:
    test_parse_datastore_repos_ignores_inactive_artifact_uris()
    print("OK: check-badge-state parser tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
