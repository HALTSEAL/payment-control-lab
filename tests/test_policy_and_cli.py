# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
import json
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from examples.fixture_policy import decide
from examples.route_retry_policy import decide as retry_decide
from payment_control_lab import __version__
from payment_control_lab.challenges import check_policy, load_policy
from payment_control_lab.input import InputError
from payment_control_lab.report import money, render_html, write_report
from payment_control_lab.scenarios import run_demo

ROOT = Path(__file__).resolve().parents[1]


class PolicyTests(unittest.TestCase):
    def test_stateless_fixture_example_matches_independent_cases(self):
        report = check_policy(decide, "fixture")
        self.assertEqual(report["summary"]["verdict"], "EXPECTATIONS_MET")
        self.assertEqual(len(report["policy_cases"]), 16)

    def test_per_route_retry_fails_cross_route_cases(self):
        report = check_policy(retry_decide, "per-route")
        row = next(r for r in report["policy_cases"] if r["case_id"] == "unknown-cross-route")
        self.assertEqual(row["status"], "MISMATCH")
        self.assertEqual(report["summary"]["verdict"], "EXPECTATIONS_NOT_MET")

    def test_always_accept_does_not_pass(self):
        self.assertEqual(check_policy(lambda _: "ACCEPT", "always-accept")["summary"]["verdict"], "EXPECTATIONS_NOT_MET")

    def test_always_refuse_does_not_pass_valid_payment_cases(self):
        report = check_policy(lambda _: "REFUSE", "always-refuse")
        self.assertEqual(report["summary"]["verdict"], "EXPECTATIONS_NOT_MET")
        self.assertTrue(any(r["status"] == "MISMATCH" and r["case_id"] == "first-payment" for r in report["policy_cases"]))

    def test_unknown_return_values_are_inconclusive(self):
        for value in (None, True, {}, "accept", "UNKNOWN"):
            with self.subTest(value=value):
                report = check_policy(lambda _: value, "invalid")
                self.assertEqual(report["summary"]["verdict"], "INCONCLUSIVE")

    def test_callback_errors_do_not_leak_exception_messages(self):
        def broken(context):
            raise ValueError("secret-example-do-not-print")
        report = check_policy(broken, "broken")
        self.assertEqual(report["summary"]["verdict"], "INCONCLUSIVE")
        self.assertNotIn("secret-example-do-not-print", json.dumps(report))

    def test_context_mutation_does_not_change_fixture_expectations(self):
        def mutate(context):
            context.clear()
            return "ACCEPT"
        self.assertEqual(check_policy(mutate, "mutating")["summary"]["verdict"], "EXPECTATIONS_NOT_MET")
        self.assertEqual(check_policy(decide, "after-mutation")["summary"]["verdict"], "EXPECTATIONS_MET")

    def test_policy_system_exit_is_inconclusive_instead_of_success(self):
        def exiting(context):
            raise SystemExit(0)
        report = check_policy(exiting, "exiting")
        self.assertEqual(report["summary"]["verdict"], "INCONCLUSIVE")
        self.assertTrue(all(r["error_type"] == "SystemExit" for r in report["policy_cases"]))

    def test_import_system_exit_is_a_configuration_error(self):
        with patch("payment_control_lab.challenges.importlib.import_module", side_effect=SystemExit(0)), self.assertRaises(InputError):
            load_policy("exiting_module:decide")

    def test_policy_import_rejects_expressions_and_noncallables(self):
        for spec in ("os:system('anything')", "examples.fixture_policy:missing", "payment_control_lab:__version__"):
            with self.subTest(spec=spec), self.assertRaises(InputError):
                load_policy(spec)


class ReportTests(unittest.TestCase):
    def test_report_escapes_user_text_and_has_no_scripts_or_external_assets(self):
        report = run_demo("held-backup")
        report["workflow_name"] = '<script>alert("example")</script>'
        report["scope"]["routes"][0]["label"] = '<img src="https://example.invalid/pixel">'
        rendered = render_html(report)
        self.assertNotIn("<script", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("Content-Security-Policy", rendered)
        self.assertNotIn("<link", rendered)

    def test_no_finding_report_retains_limits_and_optional_assessment(self):
        rendered = render_html(run_demo("held-backup"))
        self.assertIn("No finding in this trace", rendered)
        self.assertIn("does not authenticate", rendered)
        self.assertIn("Optional paid workflow assessment", rendered)
        self.assertIn("does not upload", rendered)

    def test_report_bytes_are_deterministic(self):
        self.assertEqual(render_html(run_demo()), render_html(run_demo()))

    def test_integer_money_display_does_not_round_or_assume_two_decimals(self):
        self.assertEqual(money({"amount_minor": 123456, "minor_unit_exponent": 3, "currency": "KWD"}), "KWD 123.456")
        self.assertEqual(money({"amount_minor": 1500, "minor_unit_exponent": 0, "currency": "JPY"}), "JPY 1,500")
        self.assertEqual(money({"amount_minor": 9007199254740991, "minor_unit_exponent": 2, "currency": "USD"}), "USD 90,071,992,547,409.91")

    def test_report_cannot_overwrite_input(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            path.write_text("original")
            with self.assertRaises(InputError):
                write_report(run_demo(), Path(temp), path)
            self.assertEqual(path.read_text(encoding="utf-8"), "original")

    def test_report_refuses_symlink_output(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            target = out / "target.json"
            target.write_text("original")
            try:
                (out / "report.json").symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable")
            with self.assertRaises(InputError):
                write_report(run_demo(), out)
            self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_nonfile_output_is_rejected_before_replacing_the_other_report(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "report.html").write_text("previous HTML")
            (out / "report.json").mkdir()
            with self.assertRaises(InputError):
                write_report(run_demo(), out)
            self.assertEqual((out / "report.html").read_text(encoding="utf-8"), "previous HTML")

    def test_late_write_failure_restores_the_previous_report_pair(self):
        self.assert_failed_pair_restored(existing=True)

    def test_late_write_failure_removes_new_partial_report_pair(self):
        self.assert_failed_pair_restored(existing=False)

    def assert_failed_pair_restored(self, existing):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            targets = [out / "report.html", out / "report.json"]
            if existing:
                for target in targets:
                    target.write_text("previous " + target.name)
            replace = os.replace
            def fail_second_install(source, target):
                if Path(source).name == "report.json" and Path(target) == targets[1]:
                    raise OSError("simulated second write failure")
                return replace(source, target)
            with patch("payment_control_lab.report.os.replace", side_effect=fail_second_install), self.assertRaises(InputError):
                write_report(run_demo(), out)
            for target in targets:
                if existing:
                    self.assertEqual(target.read_text(encoding="utf-8"), "previous " + target.name)
                else:
                    self.assertFalse(target.exists())

    def test_recorded_finding_takes_priority_over_missing_scope_in_next_step(self):
        report = run_demo("lost-response")
        finding = next(f for f in report["findings"] if f["category"] == "control_gap")
        report["findings"].insert(0, {"category": "evidence_gap", "summary": "Scope incomplete", "next_step": "Get missing records", "code": "UNOBSERVED_ROUTE"})
        rendered = render_html(report)
        next_panel = rendered.split('class="panel next"', 1)[1].split('</section>', 1)[0]
        self.assertIn(finding["next_step"], next_panel)
        self.assertNotIn("Get missing records", next_panel)

    def test_bundled_diagnostics_do_not_attempt_network_access(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")), patch.object(socket, "socket", side_effect=AssertionError("network")):
            run_demo()
            render_html(check_policy(decide, "fixture"))


class CLITests(unittest.TestCase):
    def call(self, *args, cwd=ROOT):
        return subprocess.run([sys.executable, str(ROOT / "lab.py"), *map(str, args)], cwd=cwd, capture_output=True, text=True, timeout=15)

    def test_clean_quickstart_creates_parseable_reports(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "demo"
            result = self.call("demo", "--out", out)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["diagnoses_reproduced"], 16)
            self.assertTrue((out / "report.html").exists())
            self.assertIn("Synthetic data", (out / "report.html").read_text(encoding="utf-8"))

    def test_review_exit_codes_distinguish_findings_evidence_and_no_finding(self):
        with TemporaryDirectory() as temp:
            for name, code in (("lost-response", 2), ("held-backup", 0), ("missing-decision", 3)):
                with self.subTest(name=name):
                    path = ROOT / "payment_control_lab" / "data" / "traces" / f"{name}.json"
                    result = self.call("review", path, "--out", Path(temp) / name)
                    self.assertEqual(result.returncode, code, result.stderr)

    def test_invalid_json_is_error_one_and_does_not_create_pass_report(self):
        with TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.json"
            bad.write_text("not-json")
            out = Path(temp) / "out"
            result = self.call("review", bad, "--out", out)
            self.assertEqual(result.returncode, 1)
            self.assertFalse((out / "report.html").exists())
            self.assertNotIn("Traceback", result.stderr)

    def test_invalid_unicode_input_is_reported_without_a_traceback(self):
        with TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.json"
            trace = json.loads((ROOT / "examples" / "workflow.json").read_text(encoding="utf-8"))
            trace["workflow_name"] = "\ud800"
            bad.write_text(json.dumps(trace), encoding="utf-8")
            out = Path(temp) / "out"
            result = self.call("review", bad, "--out", out)
            self.assertEqual(result.returncode, 1)
            self.assertFalse((out / "report.html").exists())
            self.assertNotIn("Traceback", result.stderr)

    def test_template_is_valid_but_inconclusive_and_cannot_overwrite(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / "workflow.json"
            result = self.call("template", "--out", target)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.call("review", target, "--out", Path(temp) / "out").returncode, 3)
            before = target.read_bytes()
            self.assertEqual(self.call("template", "--out", target).returncode, 1)
            self.assertEqual(before, target.read_bytes())

    def test_policy_cli_reports_expected_mismatches(self):
        with TemporaryDirectory() as temp:
            result = self.call("check-policy", "examples.route_retry_policy:decide", "--out", temp)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("Fixture expectations not met", result.stdout)

    def test_policy_exit_zero_does_not_make_the_cli_report_success(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "exiting_policy.py").write_text("def decide(context):\n    raise SystemExit(0)\n")
            result = self.call("check-policy", "exiting_policy:decide", "--out", root / "out", cwd=root)
            self.assertEqual(result.returncode, 3, result.stderr)
            report = json.loads((root / "out/report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["verdict"], "INCONCLUSIVE")

    def test_module_entrypoint(self):
        result = subprocess.run([sys.executable, "-m", "payment_control_lab", "--version"], cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0)
        self.assertIn(__version__, result.stdout)


if __name__ == "__main__":
    unittest.main()
