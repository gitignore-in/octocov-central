#!/usr/bin/env python3
"""Fail closed when configured octocov source artifacts are unavailable."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ARTIFACT_RE = re.compile(
    r"^\s*-\s*artifact://([^/\s]+)/([^/\s]+)/(.+?)\s*(?:#.*)?$"
)
DEFAULT_ALLOWED_OWNER = "gitignore-in"
DEFAULT_API_URL = "https://api.github.com"


class ArtifactError(RuntimeError):
    pass


def emit_error(title: str, message: str) -> None:
    print(f"::error title={title}::{message}", file=sys.stderr)


def parse_artifact_sources(config_path: Path) -> list[tuple[str, str, str]]:
    sources: list[tuple[str, str, str]] = []
    for line in config_path.read_text(encoding="utf-8").splitlines():
        match = ARTIFACT_RE.match(line)
        if match:
            owner, repo, artifact_name = match.groups()
            sources.append((owner, repo, artifact_name.strip()))

    if not sources:
        raise ArtifactError(f"{config_path} has no artifact:// datastores")

    return sources


def parse_link_header(link_header: str | None) -> dict[str, str]:
    links: dict[str, str] = {}
    if not link_header:
        return links

    for part in link_header.split(","):
        section = part.strip().split(";")
        if len(section) < 2:
            continue
        url = section[0].strip()
        rel = section[1].strip()
        if (
            url.startswith("<")
            and url.endswith(">")
            and rel.startswith('rel="')
            and rel.endswith('"')
        ):
            links[rel[5:-1]] = url[1:-1]
    return links


def get_json_pages(api_url: str, token: str | None, path: str) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    url = f"{api_url.rstrip('/')}/{path.lstrip('/')}"

    while url:
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "octocov-central-artifact-check",
                "X-GitHub-Api-Version": "2022-11-28",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                pages.append(json.loads(response.read().decode("utf-8")))
                url = parse_link_header(response.headers.get("Link")).get("next", "")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ArtifactError(
                f"GitHub API returned HTTP {exc.code} for {url}: {body}"
            ) from exc
        except URLError as exc:
            raise ArtifactError(f"Cannot reach GitHub API for {url}: {exc}") from exc

    return pages


def get_repo_default_branch(
    api_url: str,
    token: str | None,
    owner: str,
    repo: str,
) -> str:
    pages = get_json_pages(api_url, token, f"repos/{owner}/{repo}")
    repo_info = pages[0] if pages else {}
    default_branch = repo_info.get("default_branch")
    if not default_branch:
        raise ArtifactError(f"{owner}/{repo} has no default branch metadata")
    return default_branch


def select_latest_artifact(
    artifacts: list[dict[str, Any]],
    default_branch: str,
) -> dict[str, Any] | None:
    selected = [
        artifact
        for artifact in artifacts
        if artifact.get("expired") is False
        and (artifact.get("workflow_run") or {}).get("head_branch") == default_branch
    ]
    selected.sort(
        key=lambda artifact: (
            artifact.get("created_at") or "",
            artifact.get("id") or 0,
        ),
        reverse=True,
    )
    return selected[0] if selected else None


def latest_default_branch_artifact(
    api_url: str,
    token: str | None,
    owner: str,
    repo: str,
    artifact_name: str,
    default_branch: str,
) -> dict[str, Any] | None:
    query = urlencode({"per_page": "100", "name": artifact_name})
    pages = get_json_pages(api_url, token, f"repos/{owner}/{repo}/actions/artifacts?{query}")
    artifacts = [
        artifact
        for page in pages
        for artifact in page.get("artifacts", [])
        if artifact.get("name") == artifact_name
    ]
    return select_latest_artifact(artifacts, default_branch)


def artifact_metadata(
    source: str,
    owner: str,
    repo: str,
    artifact_name: str,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    workflow_run = artifact.get("workflow_run") or {}
    return {
        "source": source,
        "repository": f"{owner}/{repo}",
        "artifact_name": artifact_name,
        "artifact_id": artifact.get("id"),
        "digest": artifact.get("digest"),
        "size_in_bytes": artifact.get("size_in_bytes"),
        "created_at": artifact.get("created_at"),
        "expires_at": artifact.get("expires_at"),
        "archive_download_url": artifact.get("archive_download_url"),
        "workflow_run": {
            "id": workflow_run.get("id"),
            "head_branch": workflow_run.get("head_branch"),
            "head_sha": workflow_run.get("head_sha"),
            "repository_id": workflow_run.get("repository_id"),
            "head_repository_id": workflow_run.get("head_repository_id"),
        },
    }


def write_json_atomic(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_path.parent,
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(".octocov.yml"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("badges/source-artifacts.json"),
    )
    parser.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL", DEFAULT_API_URL))
    parser.add_argument("--allowed-owner", action="append", default=[DEFAULT_ALLOWED_OWNER])
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    sources = parse_artifact_sources(args.config)
    metadata: list[dict[str, Any]] = []

    for owner, repo, artifact_name in sources:
        source = f"artifact://{owner}/{repo}/{artifact_name}"
        if owner not in args.allowed_owner:
            emit_error(
                "Untrusted octocov artifact owner",
                f"{source} is outside allowed owners: {', '.join(args.allowed_owner)}",
            )
            return 1

        default_branch = get_repo_default_branch(args.api_url, token, owner, repo)
        artifact = latest_default_branch_artifact(
            args.api_url,
            token,
            owner,
            repo,
            artifact_name,
            default_branch,
        )
        if artifact is None:
            emit_error(
                "Missing octocov artifact",
                f"{source} has no unexpired artifact on default branch {default_branch}",
            )
            return 1
        metadata.append(artifact_metadata(source, owner, repo, artifact_name, artifact))

    payload = {
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "sources": metadata,
    }
    write_json_atomic(args.output, payload)
    print(f"Checked {len(metadata)} octocov source artifacts")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArtifactError as exc:
        emit_error("Octocov source artifact check failed", str(exc))
        raise SystemExit(1)
