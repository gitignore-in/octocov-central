#!/usr/bin/env python3
"""Validate the README badge Markdown and raw URL trust boundary."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit


EXPECTED_OWNER = "gitignore-in"
EXPECTED_REPO = "octocov-central"
EXPECTED_BADGE_PREFIX = (
    f"https://raw.githubusercontent.com/{EXPECTED_OWNER}/{EXPECTED_REPO}/main/badges/"
)
EXPECTED_METRICS = {"coverage", "ratio", "time"}

_DATASTORE_PATH = ("central", "reports", "datastores")
_YAML_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*$")
_ARTIFACT_DATASTORE_RE = re.compile(
    r"^-\s*['\"]?artifact://([^\s/#'\"]+/[^\s/#'\"]+)/"
)
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


class ContractError(RuntimeError):
    pass


def parse_datastore_repos(octocov_path: Path) -> set[str]:
    """Return set of 'owner/repo' strings from central.reports.datastores."""
    result = set()
    stack: list[tuple[int, str]] = []

    for line in octocov_path.read_text(encoding="utf-8").splitlines():
        content = line.split("#", 1)[0].rstrip()
        if not content.strip():
            continue

        indent = len(content) - len(content.lstrip(" "))
        stripped = content.lstrip()
        while stack and indent <= stack[-1][0]:
            stack.pop()

        key_match = _YAML_KEY_RE.match(stripped)
        if key_match:
            stack.append((indent, key_match.group(1)))
            continue

        if tuple(key for _, key in stack) != _DATASTORE_PATH:
            continue

        datastore_match = _ARTIFACT_DATASTORE_RE.match(stripped)
        if datastore_match:
            result.add(datastore_match.group(1))

    return result


def extract_markdown_image_urls(readme_path: Path) -> list[tuple[str, tuple[int, int]]]:
    """Return Markdown image URLs and their spans from README.md."""
    text = readme_path.read_text(encoding="utf-8")
    return [
        (match.group(1), match.span())
        for match in _MARKDOWN_IMAGE_RE.finditer(text)
    ]


def validate_readme_contract(
    octocov_path: Path,
    readme_path: Path,
) -> None:
    configured_repos = parse_datastore_repos(octocov_path)
    markdown_urls = extract_markdown_image_urls(readme_path)
    readme_text = readme_path.read_text(encoding="utf-8")

    if not markdown_urls:
        raise ContractError("README.md does not contain any Markdown image badges")

    badge_spans = [
        span for url, span in markdown_urls if url.startswith(EXPECTED_BADGE_PREFIX)
    ]
    if not badge_spans:
        raise ContractError("README.md does not contain any raw badge URLs")

    seen_repos: set[str] = set()
    for url, span in markdown_urls:
        if not url.startswith(EXPECTED_BADGE_PREFIX):
            continue

        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com":
            raise ContractError(f"Unexpected badge URL scheme or host: {url}")

        parts = [segment for segment in parsed.path.split("/") if segment]
        if len(parts) != 7:
            raise ContractError(f"Unexpected badge URL path shape: {url}")
        if parts[:4] != [EXPECTED_OWNER, EXPECTED_REPO, "main", "badges"]:
            raise ContractError(f"Unexpected badge URL prefix: {url}")

        owner_segment, repo_segment, metric_file = parts[4:]
        owner = unquote(owner_segment)
        repo = unquote(repo_segment)
        metric = unquote(metric_file)
        repo_key = f"{owner}/{repo}"

        if repo_key not in configured_repos:
            raise ContractError(f"Badge URL points at an unconfigured repo: {url}")

        if metric not in {f"{name}.svg" for name in EXPECTED_METRICS}:
            raise ContractError(f"Unexpected badge metric in URL: {url}")

        if quote(owner, safe="") != owner_segment:
            raise ContractError(f"Owner segment is not percent-encoded correctly: {url}")
        if quote(repo, safe="") != repo_segment:
            raise ContractError(f"Repo segment is not percent-encoded correctly: {url}")
        if quote(metric, safe="") != metric_file:
            raise ContractError(f"Metric segment is not percent-encoded correctly: {url}")

        seen_repos.add(repo_key)

    missing_repos = configured_repos - seen_repos
    if missing_repos:
        raise ContractError(
            "README.md is missing badge URLs for configured repos: "
            + ", ".join(sorted(missing_repos))
        )

    prefix_occurrences = [
        match.start()
        for match in re.finditer(re.escape(EXPECTED_BADGE_PREFIX), readme_text)
    ]
    if not prefix_occurrences:
        raise ContractError("README.md does not reference the expected badge host")

    for occurrence in prefix_occurrences:
        if not any(start <= occurrence < end for _, (start, end) in markdown_urls):
            raise ContractError(
                "README.md contains a raw badge URL outside Markdown image syntax"
            )


def main() -> int:
    repo_root = Path(__file__).parent.parent
    octocov_path = repo_root / ".octocov.yml"
    readme_path = repo_root / "README.md"

    if not octocov_path.exists():
        print("ERROR: .octocov.yml not found", file=sys.stderr)
        return 1
    if not readme_path.exists():
        print("ERROR: README.md not found", file=sys.stderr)
        return 1

    try:
        validate_readme_contract(octocov_path, readme_path)
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("OK: README badge contract matches .octocov.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
