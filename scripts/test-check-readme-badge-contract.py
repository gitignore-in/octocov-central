#!/usr/bin/env python3
"""Regression tests for check-readme-badge-contract.py."""

import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def load_module():
    module_path = Path(__file__).with_name("check-readme-badge-contract.py")
    spec = importlib.util.spec_from_file_location("check_readme_badge_contract", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_readme_contract_accepts_segment_encoded_badge_urls() -> None:
    module = load_module()
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        octocov_path = tmpdir_path / ".octocov.yml"
        readme_path = tmpdir_path / "README.md"

        octocov_path.write_text(
            """\
central:
  reports:
    datastores:
      - artifact://gitignore-in/gitignore-in/octocov-report
      - artifact://gitignore-in/example%23repo/octocov-report
  badges:
    datastores:
      - local://badges
""",
            encoding="utf-8",
        )
        readme_path.write_text(
            """\
| Repository | Badges |
| --- | --- |
| [gitignore-in/gitignore-in](https://github.com/gitignore-in/gitignore-in) | ![Coverage](https://raw.githubusercontent.com/gitignore-in/octocov-central/main/badges/gitignore-in/gitignore-in/coverage.svg) |
| [gitignore-in/example%23repo](https://github.com/gitignore-in/example%23repo) | ![Coverage](https://raw.githubusercontent.com/gitignore-in/octocov-central/main/badges/gitignore-in/example%2523repo/coverage.svg) |
""",
            encoding="utf-8",
        )

        module.validate_readme_contract(octocov_path, readme_path)


def test_validate_readme_contract_rejects_unencoded_badge_segment() -> None:
    module = load_module()
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        octocov_path = tmpdir_path / ".octocov.yml"
        readme_path = tmpdir_path / "README.md"

        octocov_path.write_text(
            """\
central:
  reports:
    datastores:
      - artifact://gitignore-in/example%23repo/octocov-report
  badges:
    datastores:
      - local://badges
""",
            encoding="utf-8",
        )
        readme_path.write_text(
            """\
| Repository | Badges |
| --- | --- |
| [gitignore-in/example%23repo](https://github.com/gitignore-in/example%23repo) | ![Coverage](https://raw.githubusercontent.com/gitignore-in/octocov-central/main/badges/gitignore-in/example%23repo/coverage.svg) |
""",
            encoding="utf-8",
        )

        try:
            module.validate_readme_contract(octocov_path, readme_path)
        except module.ContractError:
            return
        raise AssertionError("Expected ContractError for unencoded badge segment")


def main() -> int:
    test_validate_readme_contract_accepts_segment_encoded_badge_urls()
    test_validate_readme_contract_rejects_unencoded_badge_segment()
    print("OK: check-readme-badge-contract parser tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
