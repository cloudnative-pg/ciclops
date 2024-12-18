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

import unittest
import summarize_test_results
import datetime


class TestIsFailed(unittest.TestCase):
    summary = summarize_test_results.compute_test_summary("few-artifacts")

    def test_compute_summary(self):
        self.maxDiff = None
        self.assertEqual(self.summary["total_run"], 3)
        self.assertEqual(self.summary["total_failed"], 1)

        self.assertEqual(
            self.summary["by_code"]["total"],
            {"/Users/myuser/repos/cloudnative-pg/tests/e2e/initdb_test.go:80": 1},
            "unexpected summary",
        )
        self.assertEqual(
            self.summary["by_code"]["tests"],
            {
                "/Users/myuser/repos/cloudnative-pg/tests/e2e/initdb_test.go:80": {
                    "InitDB settings - initdb custom post-init SQL scripts -- can find the"
                    " tables created by the post-init SQL queries": True
                }
            },
            "unexpected summary",
        )
        self.assertEqual(
            self.summary["by_matrix"], {"total": {"id1": 3}, "failed": {"id1": 1}}
        )
        self.assertEqual(
            self.summary["by_k8s"], {"total": {"1.22": 3}, "failed": {"1.22": 1}}
        )
        self.assertEqual(
            self.summary["by_platform"], {"total": {"local": 3}, "failed": {"local": 1}}
        )
        self.assertEqual(
            self.summary["by_postgres"],
            {"total": {"PostgreSQL-11.1": 3}, "failed": {"PostgreSQL-11.1": 1}},
        )
        self.assertEqual(
            self.summary["suite_durations"],
            {
                "end_time": {
                    "local": {"id1": datetime.datetime(2021, 11, 29, 18, 31, 7)}
                },
                "start_time": {
                    "local": {"id1": datetime.datetime(2021, 11, 29, 18, 28, 37)}
                },
            },
        )

    def test_compute_thermometer(self):
        self.maxDiff = None
        thermometer = summarize_test_results.compute_thermometer_on_metric(
            self.summary, "by_platform"
        )

        self.assertEqual(
            thermometer,
            "Platforms thermometer:\n\n"
            "- 🔴 - local: 66.6% success.\t(1 out of 3 tests failed)\n\n",
        )

        thermometerPlaintext = summarize_test_results.compute_thermometer_on_metric(
            self.summary, "by_platform", False
        )

        self.assertEqual(
            thermometerPlaintext,
            "Platforms thermometer:\n\n"
            "- :red_circle: - local: 66.6% success.\t(1 out of 3 tests failed)\n\n",
        )

    def test_compute_systematic_failures(self):
        self.maxDiff = None

        for metric in ["by_test", "by_k8s", "by_postgres", "by_platform"]:
            has_alerts, out = (
                summarize_test_results.compute_systematic_failures_on_metric(
                    self.summary, metric
                )
            )
            self.assertEqual(has_alerts, False)
            self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
