# Versioning and Compatibility Policy

This document describes the compatibility commitments for the three public surfaces
that this repository exposes: the badge URL paths, the `.octocov.yml` configuration
schema, and the artifact format contract between member repositories and this central
repository.

## Badge URL paths

Badge files are served at:

```
https://raw.githubusercontent.com/gitignore-in/octocov-central/main/badges/<owner>/<repo>/<metric>.svg
```

where `<metric>` is one of `coverage`, `ratio`, or `time`.

**Stability**: These paths are **not versioned** (there is no `/v1/` segment).
A breaking change to this structure — for example, a metric rename or a path
reorganisation — would silently break any external `README.md` that embeds the
raw URL.  If such a change is ever required, the process is:

1. Publish the new path alongside the old path for at least one month.
2. Open issues or pull requests against known consumers to update their URLs.
3. Remove the old path only after all known consumers have migrated.

Until a versioned path scheme is introduced, treat the current URL structure as
stable-by-convention, not stable-by-contract.

## Removing a repository (sunset process)

When a member repository is removed from `.octocov.yml` `datastores`, the
corresponding `badges/<owner>/<repo>/` directory becomes an orphan.  To retire a
member repository:

1. Add a comment in `.octocov.yml` next to the datastore entry marking the
   removal date and reason, for example:
   ```yaml
   # Removed 2026-05-01: repo archived.
   # - artifact://gitignore-in/old-repo/octocov-report
   ```
2. Delete the `badges/<owner>/<repo>/` directory in the same commit.
3. Update `README.md` to remove the row for that repository.

This three-step record keeps the intent visible in git history even after the
YAML entry is gone.

## `.octocov.yml` configuration schema

The `.octocov.yml` format is defined by upstream
[k1LoW/octocov](https://github.com/k1LoW/octocov).  This repository does not
control the schema version; it follows the schema consumed by the pinned
`k1LoW/octocov-action` version recorded in `.github/workflows/central.yml`.

When Renovate or a manual bump updates the pinned action SHA:

1. Check the upstream [octocov release notes](https://github.com/k1LoW/octocov/releases)
   for breaking changes to `.octocov.yml` field names or value formats.
2. If a field was renamed or the value format changed, update `.octocov.yml`
   before merging the bump.
3. If no breaking changes are listed, the bump is safe to merge.

The action pin comment (e.g., `# v1.5.1`) identifies the octocov release that
the current `.octocov.yml` was written and tested against.

## Artifact format contract

Member repositories publish octocov report artifacts under the name
`octocov-report`.  The central workflow reads these artifacts using the same
`k1LoW/octocov-action` version.  If a member repository upgrades its octocov
version ahead of the central pin, the artifact format may diverge.

To stay in sync:

- The central `k1LoW/octocov-action` pin and the member repository pins should
  track the same major version.
- When the central pin is bumped, check that all member repositories use a
  compatible octocov version before merging.

There is no automated cross-version check today; this is a manual review step
during Renovate bump PRs.
