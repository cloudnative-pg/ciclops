# Building, testing, releasing

The `ciclops` GitHub Action runs using a Docker container that encapsulates the
Python script that does the CI test analysis.

## Releasing

We recommend that users of Ciclops use released versions rather than `main`.
For testing, it  may be convenient to [use a full SHA](#testing-within-a-calling-github-workflow).

The procedure for cutting a release:

1. Decide on the version number (following semVer)
1. Update the [Release notes file](ReleaseNotes.md), following the convention
  in the file, i.e. the version number included in the section, and the release
  date in the first line
1. Review and merge the release notes, and create and push a new tag with the
  desired version number
1. Cut a new release in [GitHub](https://github.com/cloudnative-pg/ciclops/releases/new),
  choosing the recent tag, and pasting the relevant content from the
  Release Notes file (no need for the release date line).

## Developing and testing

You can test directly with the Python code on the `example-artifacts` directory,
where you can see some JSON artifacts in the expected format. For example:

``` shell
python summarize_test_results.py --dir example-artifacts
```

or

``` shell
GITHUB_STEP_SUMMARY=out.md python summarize_test_results.py --dir example-artifacts
```

You can build the container with

``` shell
docker build -t gh-ciclops .
```

To get a better idea of how *ciclops* will work when used in GitHub workflows,
it is useful to run locally with `act`. See
[*act* homepage](https://github.com/nektos/act) for reference.

In the `.github/workflows` directory in this repo, you will find test YAML
workflows you can run with `act`.

**WARNING**: to test with `act`, take care to use the `-b` option to **bind**
the working directory to the Docker container. The default behavior of copying
will not work properly (at least at the time of testing this, September 2022.)
Also, make sure you are using at least the *Medium* size Docker images given
that the `-slim` ones don't support Python.

The following instruction will execute all available workflows:

``` shell
act -b
```

You can see the list of all possible jobs with `act -l`.
If you want to specify a particular job in a particular workflow, do e.g.:

``` shell
act -b -j smoke_test -W .github/workflows/test.yaml
```

**NOTE**: `act` will provide a testing environment close to that of GitHub.
In particular, the variables GITHUB_STEP_SUMMARY and GITHUB_OUTPUT are
populated, and will be available to the Python script within the Docker image.

**HINT**: some workflows, like `overflow-test.yaml`, will try to upload a
CIclops output file as an artifact by using `actions/upload-artifact`.
In such cases you may have to specify a path to your artifact server by
using the `--artifact-server-path` option. For example:

``` shell
mkdir /tmp/artifacts
act -b -j overflow_test -W .github/workflows/overflow-test.yaml --artifact-server-path /tmp/artifacts
```

## Unit tests

CIclops has the beginning of a unit test suite. You can run it with:

``` sh
python3 -m unittest
```

## Testing within a calling GitHub workflow

Even with unit tests and local tests, it's good to try Ciclops code out from a
client workflow. We can use a full length commit SHA to test out changes,
before cutting out a new release.
See the [GitHub document on using third party actions](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-third-party-actions).

Example:

``` yaml
      - name: Compute the E2E test summary
        id: generate-summary
        uses: cloudnative-pg/ciclops@<FULL_LENGTH_SHA>
        with:
          artifact_directory: test-artifacts/da
```

## How it works

The files in this repository are needed for the Dockerfile to build and run, of
course. In addition, GitHub will copy the files in the **user's** GitHub
workflow location to the Dockerfile too. This is how the folder with the JSON
artifacts will get passed. When invoking with `act`, we are simulating this with
the `-b` option.

In the Dockerfile, the `COPY . .` line will include the directory with the
JSON test artifacts at build time.
See [GitHub support for Dockerfile](https://docs.github.com/en/actions/creating-actions/dockerfile-support-for-github-actions):

> Before the action executes, GitHub will mount the GITHUB_WORKSPACE directory
> on top of anything that was at that location in the Docker image and set
> GITHUB_WORKSPACE as the working directory.

**NOTE**: the behavior of the `COPY` command in Dockerfiles seems quite
finicky on whether it's done recursively or not. The invocation used,
`COPY . .`, ensures the copy is done recursively.
