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

**Branch reference stability**: The `main` branch reference embedded in badge URLs carries
the same stability commitment as the path structure.  Renaming the default branch would
silently break every embedded badge URL, and is therefore treated as a breaking change
subject to the same three-step migration process above: keep the old branch accessible for
at least one month, notify known consumers, and retire it only after migration is complete.

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

This two-step record keeps the intent visible in git history even after the
YAML entry is gone.

`README.md` does not need manual editing: the Collect workflow regenerates the
table from `.octocov.yml` on every run, so the row for the removed repository
disappears automatically on the next successful Collect run.

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

### Artifact name stability

The artifact name `octocov-report` is **stable** and forms part of this
contract, parallel to the badge URL `<metric>` values declared above.  The
central workflow looks up each member repository's artifact by exactly this
name (see `.octocov.yml` `datastores` entries).  Contributors adding a new
member repository must publish under this exact name.

If the artifact name ever needs to change — for example because upstream
octocov adopts a different naming convention — the process is:

1. Update `.octocov.yml` to accept both the old and the new name during a
   transition period.
2. Open pull requests against all member repositories to publish under the
   new name.
3. Remove the old name from `.octocov.yml` only after all member repositories
   have migrated.

A silent mismatch (central expects `octocov-report` but a member publishes
under a different name) causes the central collect job to skip that member's
data without an error, so changes to this name require coordinated migration.
