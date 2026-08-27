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


def test_validate_readme_contract_rejects_hidden_copy_snippet_as_live_badge() -> None:
    """A badge URL that only exists inside a copy-snippet code span must not
    satisfy the live-badge requirement for a configured repo."""
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
  badges:
    datastores:
      - local://badges
""",
            encoding="utf-8",
        )
        # The visible table cell lost its live badge, but the hidden
        # "Copy status badge markdown" snippet still contains the URL inside
        # a code span. This must not be treated as a live badge.
        readme_path.write_text(
            """\
| Repository | Badges |
| --- | --- |
| [gitignore-in/gitignore-in](https://github.com/gitignore-in/gitignore-in) | <details><summary>Copy status badge markdown</summary>```![Coverage](https://raw.githubusercontent.com/gitignore-in/octocov-central/main/badges/gitignore-in/gitignore-in/coverage.svg)```</details> |
""",
            encoding="utf-8",
        )

        try:
            module.validate_readme_contract(octocov_path, readme_path)
        except module.ContractError:
            return
        raise AssertionError(
            "Expected ContractError when only a hidden copy snippet contains the badge URL"
        )


def test_extract_rendered_badge_urls_excludes_code_span_duplicates() -> None:
    module = load_module()
    with TemporaryDirectory() as tmpdir:
        readme_path = Path(tmpdir) / "README.md"
        readme_path.write_text(
            """\
![Coverage](https://raw.githubusercontent.com/gitignore-in/octocov-central/main/badges/gitignore-in/gitignore-in/coverage.svg) <details><summary>Copy status badge markdown</summary>```![Coverage](https://raw.githubusercontent.com/gitignore-in/octocov-central/main/badges/gitignore-in/gitignore-in/coverage.svg)```</details>
""",
            encoding="utf-8",
        )

        all_urls = module.extract_markdown_image_urls(readme_path)
        rendered_urls = module.extract_rendered_badge_urls(readme_path)

        assert len(all_urls) == 2, f"expected 2 total matches, got {len(all_urls)}"
        assert len(rendered_urls) == 1, f"expected 1 rendered match, got {len(rendered_urls)}"


def main() -> int:
    test_validate_readme_contract_accepts_segment_encoded_badge_urls()
    test_validate_readme_contract_rejects_unencoded_badge_segment()
    test_validate_readme_contract_rejects_hidden_copy_snippet_as_live_badge()
    test_extract_rendered_badge_urls_excludes_code_span_duplicates()
    print("OK: check-readme-badge-contract parser tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
