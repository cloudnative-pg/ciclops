#
# Copyright The CloudNativePG Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Creates a summary of all the "strategy matrix" branches in GH actions that
are running the E2E Test Suite. Produces a Markdown file which can be fed into
GitHub for the Job Summary, or viewed on its own in file or standard-out.

Each test execution in each "matrix branch" in GH is uploading a JSON artifact
with the test results.
The test artifacts are normalized to avoid some of ginkgo's idiosyncrasies.

This is the JSON format of the test artifacts:

{
        "name": "my test",
        "state": "passed",
        "start_time": "timestamp",
        "end_time": "timestamp",
        "error": error,
        "error_file": errFile,
        "error_line": errLine,
        "platform": e.g. local / gke / aks…,
        "postgres_kind": postgresql / epas,
        "matrix_id": GH actions "matrix branch" id,
        "postgres_version": semver,
        "k8s_version": semver,
        "workflow_id": GH actions workflow id,
        "repo": git repo,
        "branch": git branch,
}

In a final GH action, after all the matrix branches running the E2E Test Suite
are finished, all the artifacts are downloaded to a local directory.

The code in this file iterates over all the collected JSON artifacts to produce
a summary in Markdown, which can then be rendered in GitHub using
[GitHub Job Summaries](https://github.blog/2022-05-09-supercharging-github-actions-with-job-summaries/)
"""

import argparse
from datetime import datetime
import json
import os
import pathlib
from prettytable import MARKDOWN
from prettytable import PrettyTable


def is_failed(e2e_test):
    """checks if the test failed. In ginkgo, the passing states are
    well-defined but ginkgo 1 -> 2 added new failure kinds. So, check
    for non-pass
    """
    return (
        e2e_test["state"] != "passed"
        and e2e_test["state"] != "skipped"
        and e2e_test["state"] != "ignoreFailed"
    )


def is_external_failure(e2e_test):
    """checks if the test failed for an external reason. E.g. because the
    whole suite timed out, or the user canceled execution.
    For example, in ginkgo, the status "interrupted" is used when the suite
    times out
    """
    return is_failed(e2e_test) and e2e_test["state"] != "failed"


def is_special_error(e2e_test):
    """checks if the test failed due to one of a set of well-known errors
    that may be out-of band and warrant special display in the Test Summary
    """
    special_failures = {
        "operator was restarted": True,
        "operator was renamed": True,
    }
    return "error" in e2e_test and e2e_test["error"] in special_failures


def is_ginkgo_report_failure(e2e_test):
    """checks if the ginkgo report could not be read"""
    special_tests = {
        "Open Ginkgo report": True,
    }
    return "error" in e2e_test and e2e_test["name"] in special_tests


def is_normal_failure(e2e_test):
    """checks the test failed and was not a special kind of failure"""
    return (
        is_failed(e2e_test)
        and not is_special_error(e2e_test)
        and not is_external_failure(e2e_test)
        and not is_ginkgo_report_failure(e2e_test)
    )


def is_test_artifact(test_entry):
    should_have = [
        "name",
        "state",
        "start_time",
        "end_time",
        "error",
        "error_file",
        "error_line",
        "platform",
        "postgres_kind",
        "matrix_id",
        "postgres_version",
        "k8s_version",
        "workflow_id",
        "repo",
        "branch",
    ]
    for field in should_have:
        if field not in test_entry:
            return False
    return True


def combine_postgres_data(test_entry):
    """combines Postgres kind and version of the test artifact to
    a single field called `pg_version`
    """
    pgkind = test_entry["postgres_kind"]
    pgversion = test_entry["postgres_version"]
    test_entry["pg_version"] = f"{pgkind}-{pgversion}"

    return test_entry


def track_time_taken(test_results, test_times, suite_times):
    """computes the running shortest and longest duration of
    running each kind of test
    """
    name = test_results["name"]
    # tag abnormal failures, e.g.: "[operator was restarted]  Imports with …"
    if is_external_failure(test_results):
        tag = test_results["state"]
        name = f"[{tag}] {name}"
    elif is_special_error(test_results):
        tag = test_results["error"]
        name = f"[{tag}] {name}"

    if (
        # ignore nullish datetime
        test_results["start_time"] == "0001-01-01T00:00:00Z"
        or test_results["end_time"] == "0001-01-01T00:00:00Z"
    ):
        return

    # chop off the nanoseconds part, which is too much for
    # Python `fromisoformat`
    start_frags = test_results["start_time"].split(".")
    if len(start_frags) != 2:
        return
    end_frags = test_results["end_time"].split(".")
    if len(end_frags) != 2:
        return

    # track individual test durations. Store min-max, slowest branch
    start_time = datetime.fromisoformat(start_frags[0])
    end_time = datetime.fromisoformat(end_frags[0])
    duration = end_time - start_time
    matrix_id = test_results["matrix_id"]
    if name not in test_times["max"]:
        test_times["max"][name] = duration
    if name not in test_times["min"]:
        test_times["min"][name] = duration
    if name not in test_times["slowest_branch"]:
        test_times["slowest_branch"][name] = matrix_id

    if duration > test_times["max"][name]:
        test_times["max"][name] = duration
        test_times["slowest_branch"][name] = matrix_id
    if duration < test_times["min"][name]:
        test_times["min"][name] = duration

    # track suite time.
    # For each platform-matrix branch, track the earliest start and the latest end
    platform = test_results["platform"]
    if platform not in suite_times["start_time"]:
        suite_times["start_time"][platform] = {}
    if matrix_id not in suite_times["start_time"][platform]:
        suite_times["start_time"][platform][matrix_id] = start_time
    if platform not in suite_times["end_time"]:
        suite_times["end_time"][platform] = {}
    if matrix_id not in suite_times["end_time"][platform]:
        suite_times["end_time"][platform][matrix_id] = end_time

    if start_time < suite_times["start_time"][platform][matrix_id]:
        suite_times["start_time"][platform][matrix_id] = start_time
    if suite_times["end_time"][platform][matrix_id] < end_time:
        suite_times["end_time"][platform][matrix_id] = end_time


def count_bucketed_by_test(test_results, by_test):
    """counts the successes, failures, failing versions of kubernetes,
    failing versions of postgres, bucketed by test name.
    """
    name = test_results["name"]

    if name not in by_test["total"]:
        by_test["total"][name] = 0
    by_test["total"][name] = 1 + by_test["total"][name]
    if is_failed(test_results) and not is_ginkgo_report_failure(test_results):
        if name not in by_test["failed"]:
            by_test["failed"][name] = 0
        if name not in by_test["k8s_versions_failed"]:
            by_test["k8s_versions_failed"][name] = {}
        if name not in by_test["pg_versions_failed"]:
            by_test["pg_versions_failed"][name] = {}
        if name not in by_test["platforms_failed"]:
            by_test["platforms_failed"][name] = {}
        by_test["failed"][name] = 1 + by_test["failed"][name]
        k8s_version = test_results["k8s_version"]
        pg_version = test_results["pg_version"]
        platform = test_results["platform"]
        by_test["k8s_versions_failed"][name][k8s_version] = True
        by_test["pg_versions_failed"][name][pg_version] = True
        by_test["platforms_failed"][name][platform] = True


def count_bucketed_by_code(test_results, by_failing_code):
    """buckets by failed code, with a list of tests where the assertion fails,
    and a view of the stack trace.
    """
    name = test_results["name"]
    if test_results["error"] == "" or test_results["state"] == "ignoreFailed":
        return
    # it does not make sense to show failing code that is outside of the test
    # so we skip special failures
    if not is_normal_failure(test_results):
        return

    errfile = test_results["error_file"]
    errline = test_results["error_line"]
    err_desc = f"{errfile}:{errline}"

    if err_desc not in by_failing_code["total"]:
        by_failing_code["total"][err_desc] = 0
    by_failing_code["total"][err_desc] = 1 + by_failing_code["total"][err_desc]

    if err_desc not in by_failing_code["tests"]:
        by_failing_code["tests"][err_desc] = {}
    by_failing_code["tests"][err_desc][name] = True

    if err_desc not in by_failing_code["errors"]:
        by_failing_code["errors"][err_desc] = test_results["error"]


def count_bucketed_by_special_failures(test_results, by_special_failures):
    """counts the successes, failures, failing versions of kubernetes,
    failing versions of postgres, bucketed by test name.
    """

    if not is_failed(test_results) or is_normal_failure(test_results):
        return

    failure = ""
    if is_external_failure(test_results):
        failure = test_results["state"]
    if is_special_error(test_results) or is_ginkgo_report_failure(test_results):
        failure = test_results["error"]

    test_name = test_results["name"]
    k8s_version = test_results["k8s_version"]
    pg_version = test_results["pg_version"]
    platform = test_results["platform"]

    if failure not in by_special_failures["total"]:
        by_special_failures["total"][failure] = 0
    if failure not in by_special_failures["tests_failed"]:
        by_special_failures["tests_failed"][failure] = {}
    if failure not in by_special_failures["k8s_versions_failed"]:
        by_special_failures["k8s_versions_failed"][failure] = {}
    if failure not in by_special_failures["pg_versions_failed"]:
        by_special_failures["pg_versions_failed"][failure] = {}
    if failure not in by_special_failures["platforms_failed"]:
        by_special_failures["platforms_failed"][failure] = {}

    by_special_failures["total"][failure] = 1 + by_special_failures["total"][failure]
    by_special_failures["tests_failed"][failure][test_name] = True
    by_special_failures["k8s_versions_failed"][failure][k8s_version] = True
    by_special_failures["pg_versions_failed"][failure][pg_version] = True
    by_special_failures["platforms_failed"][failure][platform] = True


def count_bucketized_stats(test_results, buckets, field_id):
    """counts the success/failures onto a bucket. This means there are two
    dictionaries: one for `total` tests, one for `failed` tests.
    """
    bucket_id = test_results[field_id]
    if bucket_id not in buckets["total"]:
        buckets["total"][bucket_id] = 0
    buckets["total"][bucket_id] = 1 + buckets["total"][bucket_id]

    if is_failed(test_results):
        if bucket_id not in buckets["failed"]:
            buckets["failed"][bucket_id] = 0
        buckets["failed"][bucket_id] = 1 + buckets["failed"][bucket_id]


def compute_bucketized_summary(parameter_buckets):
    """counts the number of buckets with failures and the
    total number of buckets
    returns (num-failed-buckets, num-total-buckets)
    """
    failed_buckets_count = 0
    total_buckets_count = 0
    for _ in parameter_buckets["total"]:
        total_buckets_count = 1 + total_buckets_count
    for _ in parameter_buckets["failed"]:
        failed_buckets_count = 1 + failed_buckets_count
    return failed_buckets_count, total_buckets_count


def compute_test_summary(test_dir):
    """iterate over the JSON artifact files in `test_dir`, and
    bucket them for comprehension.

    Returns a dictionary of dictionaries:

    {
        "total_run": 0,
        "total_failed": 0,
        "total_special_fails": 0,
        "by_test": { … },
        "by_code": { … },
        "by_special_failures": { … },
        "by_matrix": { … },
        "by_k8s": { … },
        "by_platform": { … },
        "by_postgres": { … },
        "test_durations": { … },
        "suite_durations": { … },
    }
    """

    # initialize data structures
    ############################
    total_runs = 0
    total_fails = 0
    total_special_fails = 0
    by_test = {
        "total": {},
        "failed": {},
        "k8s_versions_failed": {},
        "pg_versions_failed": {},
        "platforms_failed": {},
    }
    by_failing_code = {
        "total": {},
        "tests": {},
        "errors": {},
    }
    by_matrix = {"total": {}, "failed": {}}
    by_k8s = {"total": {}, "failed": {}}
    by_postgres = {"total": {}, "failed": {}}
    by_platform = {"total": {}, "failed": {}}

    # special failures are not due to the test having failed, but
    # to something at a higher level, like the E2E suite having been
    # cancelled, timed out, or having executed improperly
    by_special_failures = {
        "total": {},
        "tests_failed": {},
        "k8s_versions_failed": {},
        "pg_versions_failed": {},
        "platforms_failed": {},
    }

    test_durations = {"max": {}, "min": {}, "slowest_branch": {}}
    suite_durations = {"start_time": {}, "end_time": {}}

    # start computation of summary
    ##############################
    dir_listing = os.listdir(test_dir)
    for file in dir_listing:
        if pathlib.Path(file).suffix != ".json":
            continue
        path = os.path.join(test_dir, file)
        with open(path, encoding="utf-8") as json_file:
            parsed = json.load(json_file)
            if not is_test_artifact(parsed):
                # skipping non-artifacts
                continue
            test_results = combine_postgres_data(parsed)

            total_runs = 1 + total_runs
            if is_failed(test_results):
                total_fails = 1 + total_fails

            if not is_normal_failure(test_results):
                total_special_fails = 1 + total_special_fails

            # bucketing by test name
            count_bucketed_by_test(test_results, by_test)

            # bucketing by failing code
            count_bucketed_by_code(test_results, by_failing_code)

            # special failures are treated separately
            count_bucketed_by_special_failures(test_results, by_special_failures)

            # bucketing by matrix ID
            count_bucketized_stats(test_results, by_matrix, "matrix_id")

            # bucketing by k8s version
            count_bucketized_stats(test_results, by_k8s, "k8s_version")

            # bucketing by postgres version
            count_bucketized_stats(test_results, by_postgres, "pg_version")

            # bucketing by platform
            count_bucketized_stats(test_results, by_platform, "platform")

            track_time_taken(test_results, test_durations, suite_durations)

    return {
        "total_run": total_runs,
        "total_failed": total_fails,
        "total_special_fails": total_special_fails,
        "by_test": by_test,
        "by_code": by_failing_code,
        "by_special_failures": by_special_failures,
        "by_matrix": by_matrix,
        "by_k8s": by_k8s,
        "by_platform": by_platform,
        "by_postgres": by_postgres,
        "test_durations": test_durations,
        "suite_durations": suite_durations,
    }


def compile_overview(summary):
    """computes the failed vs total count for different buckets"""
    unique_failed, unique_run = compute_bucketized_summary(summary["by_test"])
    k8s_failed, k8s_run = compute_bucketized_summary(summary["by_k8s"])
    postgres_failed, postgres_run = compute_bucketized_summary(summary["by_postgres"])
    matrix_failed, matrix_run = compute_bucketized_summary(summary["by_matrix"])
    platform_failed, platform_run = compute_bucketized_summary(summary["by_platform"])
    return {
        "total_run": summary["total_run"],
        "total_failed": summary["total_failed"],
        "total_special_fails": summary["total_special_fails"],
        "unique_run": unique_run,
        "unique_failed": unique_failed,
        "k8s_run": k8s_run,
        "k8s_failed": k8s_failed,
        "postgres_run": postgres_run,
        "postgres_failed": postgres_failed,
        "matrix_failed": matrix_failed,
        "matrix_run": matrix_run,
        "platform_failed": platform_failed,
        "platform_run": platform_run,
    }


def format_alerts(summary, embed=True, file_out=None):
    """print Alerts for tests that have failed systematically

    If the `embed` argument is true, it will produce a fragment of Markdown
    to be included with the action summary.
    Otherwise, it will be output as plain text.

    We want to capture:
    - all test combinations failed (if this happens, no more investigation needed)
    - a test failed systematically (all combinations of this test failed)
    - a PG version failed systematically (all tests in that PG version failed)
    - a K8s version failed systematically (all tests in that K8s version failed)
    - a Platform failed systematically (all tests in that Platform failed)

    We require more than 1 "failure" to avoid flooding
    """
    has_systematic_failures = False

    if summary["total_run"] == summary["total_failed"]:
        if embed:
            print(f"## Alerts\n", file=file_out)
            print(f"All test combinations failed\n", file=file_out)
        else:
            print("alerts<<EOF", file=file_out)
            print(f"All test combinations failed\n", file=file_out)
            print("EOF", file=file_out)
        return

    metric_name = {
        "by_test": "Tests",
        "by_k8s": "Kubernetes versions",
        "by_postgres": "Postgres versions",
        "by_platform": "Platforms",
    }

    output = ""
    for metric in ["by_test", "by_k8s", "by_postgres", "by_platform"]:
        has_failure_in_metric = False
        for bucket_hits in summary[metric]["failed"].items():
            bucket = bucket_hits[0]  # the items() call returns (bucket, hits) pairs
            failures = summary[metric]["failed"][bucket]
            runs = summary[metric]["total"][bucket]
            if failures == runs and failures > 1:
                if not has_failure_in_metric:
                    output += f"{metric_name[metric]} with systematic failures:\n\n"
                    has_failure_in_metric = True
                    has_systematic_failures = True
                output += f"- {bucket}: ({failures} out of {runs} tests failed)\n"
        if has_failure_in_metric:
            output += f"\n"

    if not has_systematic_failures:
        return

    if embed:
        print(f"## Alerts\n", file=file_out)
        print(f"{output}", end="", file=file_out)
    else:
        print("alerts<<EOF", file=file_out)
        print(f"{output}", file=file_out)
        print("EOF", file=file_out)


def format_overview(summary, structure, file_out=None):
    """print general test metrics"""
    print("## " + structure["title"] + "\n", file=file_out)
    table = PrettyTable(align="l")
    table.field_names = structure["header"]
    table.set_style(MARKDOWN)

    for row in structure["rows"]:
        table.add_row([summary[row[1]], summary[row[2]], row[0]])
    print(table, file=file_out)


def format_bucket_table(buckets, structure, file_out=None):
    """print table with bucketed metrics, sorted by decreasing
    amount of failures.

    The structure argument contains the layout directives. E.g.
    {
        "title": "Failures by platform",
        "header": ["failed tests", "total tests", "platform"],
    }
    """
    title = structure["title"]
    anchor = structure["anchor"]
    print(f"\n<h2><a name={anchor}>{title}</a></h2>\n", file=file_out)
    table = PrettyTable(align="l")
    table.field_names = structure["header"]
    table.set_style(MARKDOWN)

    sorted_by_fail = dict(
        sorted(buckets["failed"].items(), key=lambda item: item[1], reverse=True)
    )

    for bucket in sorted_by_fail:
        table.add_row([buckets["failed"][bucket], buckets["total"][bucket], bucket])

    print(table, file=file_out)


def format_by_test(summary, structure, file_out=None):
    """print metrics bucketed by test class"""
    title = structure["title"]
    anchor = structure["anchor"]
    print(f"\n<h2><a name={anchor}>{title}</a></h2>\n", file=file_out)

    table = PrettyTable(align="l")
    table.field_names = structure["header"]
    table.set_style(MARKDOWN)

    sorted_by_fail = dict(
        sorted(
            summary["by_test"]["failed"].items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )

    for bucket in sorted_by_fail:
        failed_k8s = ", ".join(summary["by_test"]["k8s_versions_failed"][bucket].keys())
        failed_pg = ", ".join(summary["by_test"]["pg_versions_failed"][bucket].keys())
        failed_platforms = ", ".join(
            summary["by_test"]["platforms_failed"][bucket].keys()
        )
        table.add_row(
            [
                summary["by_test"]["failed"][bucket],
                summary["by_test"]["total"][bucket],
                failed_k8s,
                failed_pg,
                failed_platforms,
                bucket,
            ]
        )

    print(table, file=file_out)


def format_by_special_failure(summary, structure, file_out=None):
    """print metrics bucketed by special failure"""
    title = structure["title"]
    anchor = structure["anchor"]
    print(f"\n<h2><a name={anchor}>{title}</a></h2>\n", file=file_out)

    table = PrettyTable(align="l")
    table.field_names = structure["header"]
    table.set_style(MARKDOWN)

    sorted_by_count = dict(
        sorted(
            summary["by_special_failures"]["total"].items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )

    for bucket in sorted_by_count:
        failed_tests = ", ".join(
            summary["by_special_failures"]["tests_failed"][bucket].keys()
        )
        failed_k8s = ", ".join(
            summary["by_special_failures"]["k8s_versions_failed"][bucket].keys()
        )
        failed_pg = ", ".join(
            summary["by_special_failures"]["pg_versions_failed"][bucket].keys()
        )
        failed_platforms = ", ".join(
            summary["by_special_failures"]["platforms_failed"][bucket].keys()
        )
        table.add_row(
            [
                summary["by_special_failures"]["total"][bucket],
                bucket,
                failed_tests,
                failed_k8s,
                failed_pg,
                failed_platforms,
            ]
        )

    print(table, file=file_out)


def format_by_code(summary, structure, file_out=None):
    """print metrics bucketed by failing code"""
    title = structure["title"]
    anchor = structure["anchor"]
    print(f"\n<h2><a name={anchor}>{title}</a></h2>\n", file=file_out)

    table = PrettyTable(align="l")
    table.field_names = structure["header"]
    table.set_style(MARKDOWN)

    sorted_by_code = dict(
        sorted(
            summary["by_code"]["total"].items(),
            key=lambda item: item[1],
            reverse=True,
        )
    )

    for bucket in sorted_by_code:
        tests = ", ".join(summary["by_code"]["tests"][bucket].keys())
        # replace newlines and pipes to avoid interference with markdown tables
        errors = (
            summary["by_code"]["errors"][bucket]
            .replace("\n", "<br />")
            .replace("|", "—")
        )
        err_cell = f"<details><summary>Click to expand</summary><span>{errors}</span></details>"
        table.add_row(
            [
                summary["by_code"]["total"][bucket],
                bucket,
                tests,
                err_cell,
            ]
        )

    print(table, file=file_out)


def format_duration(duration):
    """pretty-print duration"""
    minutes = duration.seconds // 60
    seconds = duration.seconds % 60
    return f"{minutes} min {seconds} sec"


def format_durations_table(test_times, structure, file_out=None):
    """print the table of durations per test"""
    title = structure["title"]
    anchor = structure["anchor"]
    print(f"\n<h2><a name={anchor}>{title}</a></h2>\n", file=file_out)

    table = PrettyTable(align="l", max_width=80)
    table.set_style(MARKDOWN)
    table.field_names = structure["header"]

    sorted_by_longest = dict(
        sorted(test_times["max"].items(), key=lambda item: item[1], reverse=True)
    )

    for bucket in sorted_by_longest:
        name = bucket
        longest = format_duration(test_times["max"][bucket])
        shortest = format_duration(test_times["min"][bucket])
        branch = test_times["slowest_branch"][bucket]
        table.add_row([longest, shortest, branch, name])

    print(table, file=file_out)


def format_suite_durations_table(suite_times, structure, file_out=None):
    """print the table of durations for the whole suite, per platform"""
    title = structure["title"]
    anchor = structure["anchor"]
    print(f"\n<h2><a name={anchor}>{title}</a></h2>\n", file=file_out)

    table = PrettyTable(align="l", max_width=80)
    table.set_style(MARKDOWN)
    table.field_names = structure["header"]

    # we want to display a table with one row per platform, giving us the
    # shortest duration and longest duration of the suite, and the slowest branch
    # The dictionaries in `suite_durations` are keyed by platform
    suite_durations = {
        "min": {},
        "max": {},
        "slowest_branch": {},
    }
    for platform in suite_times["start_time"]:
        for matrix_id in suite_times["start_time"][platform]:
            duration = (
                suite_times["end_time"][platform][matrix_id]
                - suite_times["start_time"][platform][matrix_id]
            )
            if platform not in suite_durations["max"]:
                suite_durations["max"][platform] = duration
            if platform not in suite_durations["min"]:
                suite_durations["min"][platform] = duration
            if platform not in suite_durations["slowest_branch"]:
                suite_durations["slowest_branch"][platform] = matrix_id

            if suite_durations["max"][platform] < duration:
                suite_durations["max"][platform] = duration
                suite_durations["slowest_branch"][platform] = matrix_id
            if duration < suite_durations["min"][platform]:
                suite_durations["min"][platform] = duration

    sorted_by_longest = dict(
        sorted(suite_durations["max"].items(), key=lambda item: item[1], reverse=True)
    )

    for bucket in sorted_by_longest:
        name = bucket
        longest = format_duration(suite_durations["max"][bucket])
        shortest = format_duration(suite_durations["min"][bucket])
        branch = suite_durations["slowest_branch"][bucket]
        table.add_row([longest, shortest, branch, name])

    print(table, file=file_out)


def format_test_failures(summary, file_out=None):
    """creates the part of the test report that drills into the failures"""

    if summary["total_special_fails"] > 0:
        by_special_failures_section = {
            "title": "Special failures",
            "anchor": "by_special_failure",
            "header": [
                "failure count",
                "special failure",
                "failed tests",
                "failed K8s",
                "failed PG",
                "failed Platforms",
            ],
        }

        format_by_special_failure(
            summary, by_special_failures_section, file_out=file_out
        )

    by_test_section = {
        "title": "Failures by test",
        "anchor": "by_test",
        "header": [
            "failed runs",
            "total runs",
            "failed K8s",
            "failed PG",
            "failed Platforms",
            "test",
        ],
    }

    format_by_test(summary, by_test_section, file_out=file_out)

    by_code_section = {
        "title": "Failures by errored code",
        "anchor": "by_code",
        "header": [
            "total failures",
            "failing code location",
            "in tests",
            "error message",
        ],
    }
    format_by_code(summary, by_code_section, file_out=file_out)

    by_matrix_section = {
        "title": "Failures by matrix branch",
        "anchor": "by_matrix",
        "header": ["failed tests", "total tests", "matrix branch"],
    }

    format_bucket_table(summary["by_matrix"], by_matrix_section, file_out=file_out)

    by_k8s_section = {
        "title": "Failures by kubernetes version",
        "anchor": "by_k8s",
        "header": ["failed tests", "total tests", "kubernetes version"],
    }

    format_bucket_table(summary["by_k8s"], by_k8s_section, file_out=file_out)

    by_postgres_section = {
        "title": "Failures by postgres version",
        "anchor": "by_postgres",
        "header": ["failed tests", "total tests", "postgres version"],
    }

    format_bucket_table(summary["by_postgres"], by_postgres_section, file_out=file_out)

    by_platform_section = {
        "title": "Failures by platform",
        "anchor": "by_platform",
        "header": ["failed tests", "total tests", "platform"],
    }

    format_bucket_table(summary["by_platform"], by_platform_section, file_out=file_out)


def format_test_summary(summary, file_out=None):
    """creates a Markdown document with several tables rendering test results.
    Outputs to stdout like a good 12-factor-app citizen, unless the `file_out`
    argument is provided
    """

    print(
        "Note that there are several tables below: overview, bucketed "
        + "by several parameters, timings.",
        file=file_out,
    )
    print(file=file_out)
    if summary["total_failed"] != 0:
        print(
            "**Index**: [timing table](#user-content-timing) | "
            + "[suite timing table](#user-content-suite_timing) | "
            + "[by special failure](#user-content-by_special_failure) | "
            + "[by test](#user-content-by_test) | "
            + "[by failing code](#user-content-by_code) | "
            + "[by matrix](#user-content-by_matrix) | "
            + "[by k8s](#user-content-by_k8s) | "
            + "[by postgres](#user-content-by_postgres) | "
            + "[by platform](#user-content-by_platform)",
            file=file_out,
        )
        print(file=file_out)

    overview = compile_overview(summary)

    overview_section = {
        "title": "Overview",
        "header": ["failed", "out of", ""],
        "rows": [
            ["test combinations", "total_failed", "total_run"],
            ["unique tests", "unique_failed", "unique_run"],
            ["matrix branches", "matrix_failed", "matrix_run"],
            ["k8s versions", "k8s_failed", "k8s_run"],
            ["postgres versions", "postgres_failed", "postgres_run"],
            ["platforms", "platform_failed", "platform_run"],
        ],
    }

    format_alerts(summary, file_out=file_out)
    format_overview(overview, overview_section, file_out=file_out)

    if summary["total_failed"] == 0:
        print(file=file_out)
        print(
            "No failures, no failure stats shown. " "It's not easy being green.",
            file=file_out,
        )
        print(file=file_out)
    else:
        format_test_failures(summary, file_out=file_out)

    suite_timing_section = {
        "title": "Suite times",
        "anchor": "suite_timing",
        "header": [
            "longest taken",
            "shortest taken",
            "slowest branch",
            "platform",
        ],
    }

    format_suite_durations_table(
        summary["suite_durations"], suite_timing_section, file_out=file_out
    )

    timing_section = {
        "title": "Test times",
        "anchor": "timing",
        "header": [
            "longest taken",
            "shortest taken",
            "slowest branch",
            "test",
        ],
    }

    format_durations_table(summary["test_durations"], timing_section, file_out=file_out)


def format_short_test_summary(summary, file_out=None):
    """creates a Markdown document with a short test overview, useful as fallback
    if the proper test summary exceeds GitHub capacity.
    Outputs to stdout like a good 12-factor-app citizen, unless the `file_out`
    argument is provided
    """

    print(
        "This is an abridged test summary, in place of the full test summary which exceeds"
        + " the GitHub limit for a summary. Please look for the full summary as an Artifact.",
        file=file_out,
    )
    print(file=file_out)
    overview = compile_overview(summary)

    overview_section = {
        "title": "Overview",
        "header": ["failed", "out of", ""],
        "rows": [
            ["test combinations", "total_failed", "total_run"],
            ["unique tests", "unique_failed", "unique_run"],
            ["matrix branches", "matrix_failed", "matrix_run"],
            ["k8s versions", "k8s_failed", "k8s_run"],
            ["postgres versions", "postgres_failed", "postgres_run"],
            ["platforms", "platform_failed", "platform_run"],
        ],
    }

    format_alerts(summary, file_out=file_out)
    format_overview(overview, overview_section, file_out=file_out)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Summarize the E2E Suite results")
    parser.add_argument(
        "-d",
        "--dir",
        type=str,
        help="directory with the JSON artifacts",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=str,
        help="output file",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        help="max number of bytes in summary",
    )

    args = parser.parse_args()

    test_summary = compute_test_summary(args.dir)
    if args.out:
        with open(args.out, "w") as f:
            format_test_summary(test_summary, file_out=f)
    elif os.getenv("GITHUB_STEP_SUMMARY"):
        print("with GITHUB_STEP_SUMMARY", os.getenv("GITHUB_STEP_SUMMARY"))
        with open(os.getenv("GITHUB_STEP_SUMMARY"), "a") as f:
            format_test_summary(test_summary, file_out=f)
        if args.limit:
            print("with GITHUB_STEP_SUMMARY limit", args.limit)
            bytes = os.stat(os.getenv("GITHUB_STEP_SUMMARY")).st_size
            if bytes > args.limit:
                # we re-open the STEP_SUMMARY with "w" to wipe out previous content
                with open(os.getenv("GITHUB_STEP_SUMMARY"), "w") as f:
                    format_short_test_summary(test_summary, file_out=f)
                with open(os.getenv("GITHUB_OUTPUT"), "a") as f:
                    print(f"Overflow=full-summary.md", file=f)
                with open("full-summary.md", "w") as f:
                    format_test_summary(test_summary, file_out=f)
    else:
        format_test_summary(test_summary)

    if os.getenv("GITHUB_OUTPUT"):
        print("with GITHUB_OUTPUT", os.getenv("GITHUB_OUTPUT"))
        with open(os.getenv("GITHUB_OUTPUT"), "a") as f:
            format_alerts(test_summary, embed=False, file_out=f)
