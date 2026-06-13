#!/usr/bin/env python3
"""
Validate that badges/ directories match the configured datastores in .octocov.yml.

State machine:
  A: datastore entry present + badges/ dir present  -> OK (active)
  B: datastore entry present + badges/ dir absent   -> OK (first run pending)
  C: datastore entry absent  + badges/ dir absent   -> OK (fully retired)
  D: datastore entry absent  + badges/ dir present  -> ERROR (orphan)

Exits 0 if no state-D entries are found, 1 otherwise.
"""

import re
import sys
from pathlib import Path


_DATASTORE_PATH = ("central", "reports", "datastores")
_YAML_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*$")
_ARTIFACT_DATASTORE_RE = re.compile(
    r"^-\s*['\"]?artifact://([^\s/#'\"]+/[^\s/#'\"]+)/"
)


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


def find_badge_repos(badges_dir: Path) -> set[str]:
    """Return set of 'owner/repo' strings present under badges/."""
    result = set()
    if not badges_dir.is_dir():
        return result
    for owner_dir in badges_dir.iterdir():
        if not owner_dir.is_dir():
            continue
        for repo_dir in owner_dir.iterdir():
            if repo_dir.is_dir():
                result.add(f"{owner_dir.name}/{repo_dir.name}")
    return result


def main() -> int:
    repo_root = Path(__file__).parent.parent
    octocov_path = repo_root / ".octocov.yml"
    badges_dir = repo_root / "badges"

    if not octocov_path.exists():
        print("ERROR: .octocov.yml not found", file=sys.stderr)
        return 1

    configured = parse_datastore_repos(octocov_path)
    present = find_badge_repos(badges_dir)

    orphans = present - configured  # state D: badges/ dir without a datastore entry
    missing = configured - present  # state B: datastore entry without badges/ dir (transient, OK)

    if missing:
        print(f"INFO: {len(missing)} datastore(s) with no badges/ dir yet (state B — first run pending):")
        for repo in sorted(missing):
            print(f"  {repo}")

    if orphans:
        print(f"ERROR: {len(orphans)} orphan badges/ director(ies) with no datastore entry (state D):")
        for repo in sorted(orphans):
            print(f"  badges/{repo}/")
        print("Run the sunset process in docs/versioning.md to remove them.")
        return 1

    print(f"OK: {len(configured)} datastore(s), {len(present)} badges/ dir(s) — no orphans.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
