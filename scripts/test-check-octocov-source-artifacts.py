#!/usr/bin/env python3
"""Regression tests for check-octocov-source-artifacts.py."""

import importlib.util
import json
import sys
import tempfile
import zipfile
from io import BytesIO
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


def test_build_output_payload_preserves_timestamp_when_sources_are_unchanged() -> None:
    module = load_module()
    metadata = [{"source": "artifact://gitignore-in/example/octocov-report"}]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "source-artifacts.json"
        output_path.write_text(
            '{"generated_at":"2026-07-13T00:00:00Z","sources":'
            '[{"source":"artifact://gitignore-in/example/octocov-report"}]}',
            encoding="utf-8",
        )

        payload = module.build_output_payload(
            output_path,
            metadata,
            "2026-07-14T00:00:00Z",
        )

    assert payload["generated_at"] == "2026-07-13T00:00:00Z"
    assert payload["sources"] == metadata


def test_build_output_payload_updates_timestamp_when_sources_change() -> None:
    module = load_module()
    previous_metadata = [
        {"source": "artifact://gitignore-in/example/octocov-report", "artifact_id": 1}
    ]
    current_metadata = [
        {"source": "artifact://gitignore-in/example/octocov-report", "artifact_id": 2}
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "source-artifacts.json"
        output_path.write_text(
            json.dumps(
                {
                    "generated_at": "2026-07-13T00:00:00Z",
                    "sources": previous_metadata,
                }
            ),
            encoding="utf-8",
        )

        payload = module.build_output_payload(
            output_path,
            current_metadata,
            "2026-07-14T00:00:00Z",
        )

    assert payload["generated_at"] == "2026-07-14T00:00:00Z"
    assert payload["sources"] == current_metadata


def test_write_resolved_config_rewrites_artifact_datastores_to_local_paths() -> None:
    module = load_module()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        config_path = tmpdir_path / ".octocov.yml"
        resolved_path = tmpdir_path / "resolved.yml"
        pinned_dir = tmpdir_path / "reports" / "gitignore-in" / "gitignore-in" / "octocov-report"
        config_path.write_text(
            """central:
  reports:
    datastores:
      - artifact://gitignore-in/gitignore-in/octocov-report
      - artifact://gitignore-in/website/octocov-report # keep comment
  badges:
    datastores:
      - local://badges
""",
            encoding="utf-8",
        )

        module.write_resolved_config(
            config_path,
            resolved_path,
            {
                "artifact://gitignore-in/gitignore-in/octocov-report": module.render_local_datastore_url(pinned_dir),
                "artifact://gitignore-in/website/octocov-report": module.render_local_datastore_url(
                    tmpdir_path / "reports" / "gitignore-in" / "website" / "octocov-report"
                ),
            },
        )

        resolved_text = resolved_path.read_text(encoding="utf-8")

    assert "artifact://gitignore-in/gitignore-in/octocov-report" not in resolved_text
    assert f"- local://{pinned_dir.resolve().as_posix()}" in resolved_text
    assert "# keep comment" in resolved_text


def test_materialize_artifact_archive_extracts_zip_payload() -> None:
    module = load_module()

    class FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return self.payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    artifact_zip = BytesIO()
    with zipfile.ZipFile(artifact_zip, "w") as archive:
        archive.writestr("report.json", '{"repository":"gitignore-in/gitignore-in"}')

    original_urlopen = module.urlopen
    module.urlopen = lambda request, timeout=30: FakeResponse(artifact_zip.getvalue())
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "reports"
            module.materialize_artifact_archive(
                "https://api.github.com/repos/gitignore-in/gitignore-in/actions/artifacts/1/zip",
                "token",
                destination,
            )
            extracted = (destination / "report.json").read_text(encoding="utf-8")
    finally:
        module.urlopen = original_urlopen

    assert json.loads(extracted) == {"repository": "gitignore-in/gitignore-in"}


def main() -> int:
    test_select_latest_artifact_prefers_default_branch()
    test_select_latest_artifact_returns_none_without_default_branch_match()
    test_build_output_payload_preserves_timestamp_when_sources_are_unchanged()
    test_build_output_payload_updates_timestamp_when_sources_change()
    test_write_resolved_config_rewrites_artifact_datastores_to_local_paths()
    test_materialize_artifact_archive_extracts_zip_payload()
    print("OK: check-octocov-source-artifacts selection tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
