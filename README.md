# ciclops

👁️

*ciclops* (CI-clops) is a GitHub Action that summarizes the result of a Test
Suite executed in a series of "strategy matrix" branches, and helps orient
investigations when tests fail.

The legends tell of a mythical one-eyed creature that was cursed by the gods to
watch over Continuous Integration pipelines for all eternity.

## Inputs

- `artifact_directory`: **Required** directory holding the
  JSON artifacts representing tests.
- `output_file`: **Optional** the file where the markdown report will be
  written. If omitted, the report will be written to Standard-Out.

## Outputs

No outputs in the GitHub Actions sense. It does write a test summary in Markdown
format, either to a file or to Stdout depending on the `output_file` input.

## Usage

To use ciclops, your Test step(s) in your CI/CD pipeline should be producing
JSON artifacts with the results of each test executed.
You can find example JSON artifacts in the `example_artifacts` directory.

**NOTE**: these examples show the expected schema of the JSON artifacts. The
field names are generic and should serve you. Other fields in JSON objects will
be ignored.

If your CI/CD pipeline runs tests in several *strategy matrix* branches, you
should ensure the JSON artifacts are uploaded (e.g. via the GitHub
`actions/upload-artifact` action.)
You should add the summary creation step to fire once all branches have
finished, then download all the JSON artifacts created in the various branches,
and gather them into one directory.

With those prerequisites, you can trigger ciclops with the `artifact_directory`
argument set to the folder containing the JSON artifacts, and the `output_file`
set to write a markdown report. Then you can print that report to the
$GITHUB_STEP_SUMMARY environment variable provided by GitHub.

For example:

``` yaml
    …
    …
    steps:
      - uses: actions/checkout@v3

      - name: Create a directory for the artifacts
        run: mkdir test-artifacts

      - name: Download all artifacts to the directory
        uses: actions/download-artifact@v3
        with:
          path: test-artifacts

      - name: Flatten all artifacts onto directory
        # The download-artifact action, since we did not give it a name,
        # downloads all artifacts and creates a new folder for each.
        # In this step we bring all the JSONs to a single folder
        run: |
            mkdir test-artifacts/data
            mv test-artifacts/*/*.json test-artifacts/data

      - name: Compute the E2E test summary
        uses: cloudnative-pg/ciclops@main
        with:
          artifact_directory: test-artifacts/data
          output_file: test-summary.md

      - name: Create GitHub Job Summary from the file
        run: cat test-summary.md >> $GITHUB_STEP_SUMMARY
```

## Origin

At EDB, working on a series of Kubernetes operators for PostgreSQL, we have an
extensive test suite that is executed for a variety of combinations of
PostgreSQL and Kubernetes versions, using GitHub's *strategy matrix* construct.

When there are failures in a given run of our CI/CD pipeline, it becomes
difficult to make sense of things. With so many tests executed in so many matrix
branches, clicking into each matrix branch and drilling in to find the failing
tests quickly becomes painful.
Systemic issues often escape scrutiny, buried in data. Information is lost
like … tears in rain.

*ciclops* adds a
[job summary](https://github.blog/2022-05-09-supercharging-github-actions-with-job-summaries/)
to the GitHub Actions output of a CI/CD pipeline. It buckets tests according to
several criteria, doing the grunt work of figuring out if there was a
pattern to test failures.
It also displays a table of test durations, sorted by slowest.

## Contributing

Please read the [code of conduct](CODE_OF_CONDUCT.md) and the
[guidelines](CONTRIBUTING.md) to contribute to the project.

## Disclaimer

`ciclops` is open source software and comes "as is". Please carefully
read the [license](LICENSE) before you use this software, in particular
the "Disclaimer of Warranty" and "Limitation of Liability" items.

## Copyright

`ciclops` is distributed under Apache License 2.0.

Copyright (C) The CloudNativePG Contributors.
