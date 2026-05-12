# Metric Values

This repository publishes octocov central-mode values in `README.md` and the
SVG files under `badges/`. The values are rendered by octocov, so this document
describes how to read the generated output rather than redefining the
calculation rules.

## Coverage

`Coverage` is the coverage percentage reported by the source repository's
octocov report. It is displayed as a percentage with one decimal place, such as
`79.0%`.

Treat the displayed value as a rounded presentation value. Consumers that need
threshold decisions should use the source repository's octocov report or CI
result instead of parsing the badge text.

## Code To Test Ratio

`Code to Test Ratio` is the ratio rendered by octocov for code volume compared
with test volume. The README displays it in `1:N` form, such as `1:0.0`.

Small projects can round to `0.0` in the displayed ratio. Use it as a coarse
trend indicator, not as a precise measurement.

## Test Execution Time

`Test Execution Time` is the test duration rendered by octocov. The README and
`time.svg` badge display it in whole seconds, such as `7s`.

Sub-second changes may not be visible in the rendered badge. Use the source
repository's CI logs when precise timing is required.
