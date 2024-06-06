# Release notes for CIclops

History of user-visible changes in CIclops.

For a complete list of changes, please refer to the
[commits](https://github.com/cloudnative-pg/ciclops/commits/main)
on the `main` branch in GitHub.

## Version 1.3.0

**Release date:** Jun 06, 2024

Improvements:

- Introduce a "thermometer" color-coded view displaying the test percentage
  failure per platform, both for the GH summary and as an output that can
  be used in chatops (#10)
- Cap the number of alerts shown in chatops (max 2 per metric) (#10)
- Update the GH actions dependencies (#10)

Fixes:

- Stop overcounting kubernetes versions and failure rates in them (#10)

## Version 1.2.1

**Release date:** May 31, 2023

This is a point release to avoid getting chatops notifications
on Alerts due to false positives.

Improvements:

- Don't count as Alerts special failures such as Ginkgo report missing or suite
  canceled or timed out (#7)

## Version 1.2.0

**Release date:** April 28, 2023

Improvements:

- Leverage the GitHub env variables inside the Python code to simplify (#5)
- General improvements on tests and documentation (#5)
- Optionally create a short summary for cases where the full summary might
  exceed the allowed size in GitHub Actions (#4)
- Compute a new Alerts section with systematic failures, offer standalone for
  chatops integration (#4)
- Add unit tests (#4)

Fixes:

- Stop showing `ignoreFail` cases in the code errors table (#4)

## Version 1.1.0

**Release date:** Feb 20, 2023

Improvements:

- Make CIclops resilient to JSON files without the expected schema (#1)
- Add new tables to show failing code location, and whole-suite durations (#2)

## Version 1.0.0

**Release date:** Nov 22, 2022

Initial release of the CIclops GitHub action in the CloudNativePG project.
