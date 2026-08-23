#!/usr/bin/env python3
"""Fail closed when configured octocov source artifacts are unavailable."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


ARTIFACT_RE = re.compile(
    r"^\s*-\s*artifact://([^/\s]+)/([^/\s]+)/(.+?)\s*(?:#.*)?$"
)
RELATIVE_LOCAL_RE = re.compile(r"^\s*-\s*local://([^/\s].*?)\s*(?:#.*)?$")
DEFAULT_ALLOWED_OWNER = "gitignore-in"
DEFAULT_API_URL = "https://api.github.com"


class ArtifactError(RuntimeError):
    pass


def emit_error(title: str, message: str) -> None:
    print(f"::error title={title}::{message}", file=sys.stderr)


def github_request_headers(token: str | None) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": "octocov-central-artifact-check",
        "X-GitHub-Api-Version": "2022-11-28",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    }


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
            headers=github_request_headers(token),
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


class _StripAuthOnCrossHostRedirect(HTTPRedirectHandler):
    """GitHub artifact downloads redirect to blob storage that rejects the
    GitHub API Authorization header (HTTP 401 InvalidAuthenticationInfo)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_request is not None and urlsplit(newurl).netloc != urlsplit(req.full_url).netloc:
            new_request.remove_header("Authorization")
        return new_request


def open_artifact_url(request: Request, timeout: int = 30):
    return build_opener(_StripAuthOnCrossHostRedirect()).open(request, timeout=timeout)


def local_datastore_path(
    materialize_root: Path,
    owner: str,
    repo: str,
    artifact_name: str,
) -> Path:
    return materialize_root / owner / repo / artifact_name


def materialize_artifact_archive(
    archive_download_url: str,
    token: str | None,
    destination_dir: Path,
) -> None:
    request = Request(
        archive_download_url,
        headers=github_request_headers(token),
    )
    try:
        with open_artifact_url(request, timeout=30) as response:
            archive_bytes = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ArtifactError(
            f"GitHub artifact download returned HTTP {exc.code} for {archive_download_url}: {body}"
        ) from exc
    except URLError as exc:
        raise ArtifactError(
            f"Cannot download GitHub artifact {archive_download_url}: {exc}"
        ) from exc

    destination_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            archive.extractall(destination_dir)
    except zipfile.BadZipFile as exc:
        raise ArtifactError(
            f"GitHub artifact {archive_download_url} is not a valid zip archive"
        ) from exc


def render_local_datastore_url(path: Path) -> str:
    return f"local://{path.resolve().as_posix()}"


def write_resolved_config(
    config_path: Path,
    output_path: Path,
    replacements: dict[str, str],
) -> None:
    # octocov resolves relative local:// datastores (e.g. the badges output
    # datastore) against the directory of the --config file it was given, not
    # against the original .octocov.yml location. Since output_path lives
    # outside the repository (a runner-temp copy), any relative local://
    # entry must be rewritten to an absolute path anchored at config_path's
    # directory here, or octocov-action fails immediately trying to stat a
    # directory that never existed under the temp location.
    config_root = config_path.resolve().parent
    config_text = config_path.read_text(encoding="utf-8")
    has_explicit_central_root = bool(re.search(r"(?m)^\s{2}root:\s*\S", config_text))
    resolved_lines: list[str] = []
    for line in config_text.splitlines():
        if not has_explicit_central_root and re.match(r"^central:\s*$", line):
            # Same reasoning as the local:// rewrite below: octocov also
            # anchors the default central.root ("." when unset) at the
            # --config file's directory, which would otherwise point
            # README/index output at the runner-temp copy's directory
            # instead of the checked-out repository.
            resolved_lines.append(line)
            resolved_lines.append(f"  root: {config_root.as_posix()}")
            continue

        match = ARTIFACT_RE.match(line)
        if match:
            owner, repo, artifact_name = match.groups()
            source = f"artifact://{owner}/{repo}/{artifact_name.strip()}"
            replacement = replacements.get(source)
            if replacement is None:
                resolved_lines.append(line)
                continue

            prefix, _, suffix = line.partition("artifact://")
            source_fragment, comment_fragment = suffix, ""
            if "#" in suffix:
                source_fragment, comment_fragment = suffix.split("#", 1)
                comment_fragment = "#" + comment_fragment
            trailing_ws = source_fragment[len(source_fragment.rstrip()):]
            resolved_lines.append(
                f"{prefix}{replacement}{trailing_ws}{comment_fragment}"
            )
            continue

        local_match = RELATIVE_LOCAL_RE.match(line)
        if local_match:
            relative_path = local_match.group(1)
            replacement = render_local_datastore_url(config_root / relative_path)

            prefix, _, suffix = line.partition("local://")
            source_fragment, comment_fragment = suffix, ""
            if "#" in suffix:
                source_fragment, comment_fragment = suffix.split("#", 1)
                comment_fragment = "#" + comment_fragment
            trailing_ws = source_fragment[len(source_fragment.rstrip()):]
            resolved_lines.append(
                f"{prefix}{replacement}{trailing_ws}{comment_fragment}"
            )
            continue

        resolved_lines.append(line)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(resolved_lines) + "\n", encoding="utf-8")


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


def build_output_payload(
    output_path: Path,
    metadata: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        if (
            existing.get("sources") == metadata
            and isinstance(existing.get("generated_at"), str)
        ):
            generated_at = existing["generated_at"]

    return {
        "generated_at": generated_at,
        "sources": metadata,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(".octocov.yml"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("badges/source-artifacts.json"),
    )
    parser.add_argument(
        "--resolved-config",
        type=Path,
        default=None,
        help="Write a copy of the config with artifact:// report datastores pinned to local:// paths",
    )
    parser.add_argument(
        "--materialize-root",
        type=Path,
        default=None,
        help="Download and extract the selected artifact archives under this directory",
    )
    parser.add_argument("--api-url", default=os.environ.get("GITHUB_API_URL", DEFAULT_API_URL))
    parser.add_argument("--allowed-owner", action="append", default=[DEFAULT_ALLOWED_OWNER])
    args = parser.parse_args()

    if (args.resolved_config is None) != (args.materialize_root is None):
        raise ArtifactError(
            "--resolved-config and --materialize-root must be provided together"
        )

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    sources = parse_artifact_sources(args.config)
    metadata: list[dict[str, Any]] = []
    replacements: dict[str, str] = {}

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
        source_metadata = artifact_metadata(source, owner, repo, artifact_name, artifact)
        metadata.append(source_metadata)
        if args.materialize_root is not None:
            archive_download_url = source_metadata.get("archive_download_url")
            if not isinstance(archive_download_url, str) or not archive_download_url:
                raise ArtifactError(f"{source} is missing archive_download_url metadata")
            destination_dir = local_datastore_path(
                args.materialize_root,
                owner,
                repo,
                artifact_name,
            )
            materialize_artifact_archive(
                archive_download_url,
                token,
                destination_dir,
            )
            replacements[source] = render_local_datastore_url(destination_dir)

    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    payload = build_output_payload(args.output, metadata, generated_at)
    write_json_atomic(args.output, payload)
    print(f"Checked {len(metadata)} octocov source artifacts")
    print(f"Wrote {args.output}")
    if args.resolved_config is not None:
        write_resolved_config(args.config, args.resolved_config, replacements)
        print(f"Wrote {args.resolved_config}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArtifactError as exc:
        emit_error("Octocov source artifact check failed", str(exc))
        raise SystemExit(1)
