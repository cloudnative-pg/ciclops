# Building and testing locally

The `ciclops` GitHub Action runs using a Docker container that encapsulates the
Python script that does the CI test analysis.

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

The following instruction will execute all available workflows:

``` shell
act -b
```

You can see the list of all possible jobs with `act -l`.
If you want to specify a particular job in a particular workflow, do e.g.:

``` shell
act -b -j overflow_test -W .github/workflows/overflow-test.yaml
```

NOTE: `act` will provide a testing environment close to that of GitHub. In
particular, the variables GITHUB_STEP_SUMMARY and GITHUB_OUTPUT are
populated, and will be available to the Python script within the Docker image.

## Unit tests

CIclops has the beginning of a unit test suite. You can run it with:

``` sh
python3 -m unittest
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
