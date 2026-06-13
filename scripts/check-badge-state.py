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


def parse_datastore_repos(octocov_path: Path) -> set[str]:
    """Return set of 'owner/repo' strings from central.reports.datastores."""
    text = octocov_path.read_text()
    # Match artifact://owner/repo/... URIs. Use [^\s/]+ to avoid crossing line boundaries.
    pattern = re.compile(r"artifact://([^\s/]+/[^\s/]+)/")
    return {m.group(1) for m in pattern.finditer(text)}


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
