# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from examples.fixture_policy import decide
from examples.route_retry_policy import decide as retry_decide
from payment_control_lab.challenges import compare_policy
from payment_control_lab.cli import diagnostic_exit
from payment_control_lab.input import InputError
from payment_control_lab.owner_summary import build_owner_summary, render_owner_html
from payment_control_lab.report import render_html, write_report
from payment_control_lab.scenarios import run_demo

ROOT = Path(__file__).resolve().parents[1]


class ComparisonTests(unittest.TestCase):
    def test_repaired_policy_meets_absolute_contract_and_records_improvements(self):
        result = compare_policy(retry_decide, decide, "before", "after")
        self.assertEqual(diagnostic_exit(result), 0)
        self.assertGreater(result["comparison"]["improved_count"], 0)
        self.assertEqual(result["comparison"]["regressed_count"], 0)
        self.assertEqual(len(result["comparison_cases"]), 16)

    def test_one_regression_is_not_cancelled_by_many_improvements(self):
        def improved_except_first_payment(context):
            if not context["prior_attempts"]:
                return "REFUSE"
            return decide(context)
        result = compare_policy(retry_decide, improved_except_first_payment, "before", "after")
        self.assertGreater(result["comparison"]["improved_count"], result["comparison"]["regressed_count"])
        self.assertGreater(result["comparison"]["regressed_count"], 0)
        self.assertEqual(diagnostic_exit(result), 2)

    def test_unchanged_bad_baseline_cannot_pass(self):
        result = compare_policy(retry_decide, retry_decide, "before", "after")
        self.assertEqual(result["comparison"]["regressed_count"], 0)
        self.assertGreater(result["comparison"]["after_mismatch_count"], 0)
        self.assertEqual(diagnostic_exit(result), 2)

    def test_unchanged_good_policy_matches_without_invented_improvements(self):
        result = compare_policy(decide, decide, "before", "after")
        self.assertEqual(diagnostic_exit(result), 0)
        self.assertEqual(result["comparison"]["improved_count"], 0)

    def test_equivalent_allowed_hold_and_refuse_are_not_regressions(self):
        def conservative(context):
            value = decide(context)
            return "REFUSE" if value == "HOLD" else value
        result = compare_policy(decide, conservative, "before", "after")
        self.assertEqual(diagnostic_exit(result), 0)
        self.assertEqual(result["comparison"]["regressed_count"], 0)
        self.assertTrue(any(r["before_decision"] != r["after_decision"] for r in result["comparison_cases"]))

    def test_unknown_baseline_cannot_establish_improvement(self):
        result = compare_policy(lambda _: None, decide, "before", "after")
        self.assertEqual(result["comparison"]["after_verdict"], "EXPECTATIONS_MET")
        self.assertEqual(result["comparison"]["improved_count"], 0)
        self.assertEqual(result["comparison"]["uncertain_count"], 16)
        self.assertEqual(diagnostic_exit(result), 3)

    def test_broken_candidate_is_inconclusive_and_exception_text_is_omitted(self):
        def broken(context):
            raise ValueError("DO_NOT_DISCLOSE_CALLBACK_DETAIL")
        result = compare_policy(decide, broken, "before", "after")
        self.assertEqual(diagnostic_exit(result), 3)
        self.assertNotIn("DO_NOT_DISCLOSE_CALLBACK_DETAIL", json.dumps(result))

    def test_candidate_mismatch_takes_priority_over_unknown_baseline(self):
        result = compare_policy(lambda _: None, retry_decide, "before", "after")
        self.assertEqual(diagnostic_exit(result), 2)
        self.assertEqual(result["summary"]["evidence_gap_count"], 16)

    def test_both_callback_roles_retain_error_types_without_messages(self):
        def before(context):
            raise RuntimeError("DO_NOT_DISCLOSE_BASELINE_DETAIL")
        def after(context):
            raise ValueError("DO_NOT_DISCLOSE_CANDIDATE_DETAIL")
        result = compare_policy(before, after, "before", "after")
        for row in result["comparison_cases"]:
            self.assertEqual(row["before_error_type"], "RuntimeError")
            self.assertEqual(row["after_error_type"], "ValueError")
        self.assertEqual(diagnostic_exit(result), 3)
        self.assertNotIn("DO_NOT_DISCLOSE", json.dumps(result))

    def test_before_context_mutation_cannot_change_candidate_or_expectations(self):
        def mutating_before(context):
            answer = decide(context)
            context.clear()
            return answer
        result = compare_policy(mutating_before, decide, "before", "after")
        self.assertEqual(diagnostic_exit(result), 0)
        self.assertTrue(all(row["before_status"] == row["after_status"] == "MATCH" for row in result["comparison_cases"]))


class RepeatableCLITests(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "lab.py"), *map(str, args)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=15)

    def test_comparison_command_creates_candidate_and_owner_results(self):
        with TemporaryDirectory() as temp:
            result = self.call("compare-policy", "examples.route_retry_policy:decide", "examples.fixture_policy:decide", "--out", temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(temp) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["kind"], "policy_comparison")
            self.assertEqual(report["owner_summary"]["comparison"], report["comparison"])
            self.assertTrue((Path(temp) / "owner-summary.html").is_file())

    def test_advisory_policy_keeps_mismatch_verdict_with_process_zero(self):
        with TemporaryDirectory() as temp:
            result = self.call("check-policy", "examples.route_retry_policy:decide", "--ci-mode", "report", "--out", temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(temp) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["verdict"], "EXPECTATIONS_NOT_MET")
            self.assertEqual(report["ci"]["diagnostic_exit_code"], 2)
            self.assertEqual(report["ci"]["process_exit_code"], 0)
            self.assertIn("Advisory completion is not an approval", (Path(temp) / "report.html").read_text(encoding="utf-8"))

    def test_advisory_history_keeps_evidence_gap(self):
        with TemporaryDirectory() as temp:
            trace = ROOT / "payment_control_lab/data/traces/missing-decision.json"
            result = self.call("review", trace, "--ci-mode", "report", "--out", temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(temp) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["verdict"], "INCONCLUSIVE")
            self.assertEqual(report["ci"]["diagnostic_exit_code"], 3)

    def test_advisory_comparison_keeps_regressions(self):
        with TemporaryDirectory() as temp:
            result = self.call("compare-policy", "examples.fixture_policy:decide", "examples.route_retry_policy:decide", "--ci-mode", "report", "--out", temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(temp) / "report.json").read_text(encoding="utf-8"))
            self.assertGreater(report["comparison"]["regressed_count"], 0)
            self.assertEqual(report["ci"]["diagnostic_exit_code"], 2)

    def test_default_gate_blocks_remaining_candidate_mismatches(self):
        with TemporaryDirectory() as temp:
            result = self.call("compare-policy", "examples.route_retry_policy:decide", "examples.route_retry_policy:decide", "--out", temp)
            self.assertEqual(result.returncode, 2)

    def test_advisory_mode_never_hides_invalid_input_or_import(self):
        with TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.json"
            bad.write_text("not json", encoding="utf-8")
            out = Path(temp) / "out"
            for args in (("review", bad), ("check-policy", "missing_policy:decide"), ("compare-policy", "missing_policy:decide", "examples.fixture_policy:decide")):
                with self.subTest(args=args):
                    result = self.call(*args, "--ci-mode", "report", "--out", out)
                    self.assertEqual(result.returncode, 1)
                    self.assertFalse((out / "report.json").exists())
                    self.assertFalse((out / "owner-summary.html").exists())

    def test_advisory_mode_never_hides_output_error(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "out"
            out.mkdir()
            (out / "owner-summary.html").mkdir()
            result = self.call("check-policy", "examples.fixture_policy:decide", "--ci-mode", "report", "--out", out)
            self.assertEqual(result.returncode, 1)
            self.assertFalse((out / "report.json").exists())

    def test_unbound_customer_adapter_is_inconclusive_in_both_ci_modes(self):
        with TemporaryDirectory() as temp:
            for mode, expected_exit in (("report", 0), ("gate", 3)):
                with self.subTest(mode=mode):
                    out = Path(temp) / mode
                    completed = self.call("check-policy", "examples.customer_adapter:decide", "--ci-mode", mode, "--out", out)
                    self.assertEqual(completed.returncode, expected_exit, completed.stderr)
                    result = json.loads((out / "report.json").read_text(encoding="utf-8"))
                    self.assertEqual(result["summary"]["verdict"], "INCONCLUSIVE")
                    self.assertEqual(result["ci"]["diagnostic_exit_code"], 3)
                    self.assertEqual(result["summary"]["evidence_gap_count"], 16)
                    self.assertEqual(result["owner_summary"]["ci"], result["ci"])

    def test_adapter_is_loaded_from_customer_root_away_from_lab_checkout(self):
        with TemporaryDirectory() as temp:
            customer = Path(temp)
            # A customer's existing function is imported from their own root.
            (customer / "payment_policy_adapter.py").write_text("def decide(context):\n    return 'ACCEPT'\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "lab.py"), "check-policy", "payment_policy_adapter:decide", "--out", "results"],
                cwd=customer, capture_output=True, text=True, encoding="utf-8", timeout=15,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            result = json.loads((customer / "results/report.json").read_text(encoding="utf-8"))
            self.assertTrue(all(row["observed_decision"] == "ACCEPT" for row in result["policy_cases"]))
            self.assertTrue((customer / "results/owner-summary.html").is_file())


class OwnerSummaryTests(unittest.TestCase):
    def test_free_follow_up_and_workflow_questions_remain_available_for_each_result(self):
        for result in (run_demo(), run_demo("lost-response"), run_demo("unobserved-portal"), compare_policy(retry_decide, decide, "before", "after")):
            with self.subTest(kind=result["kind"], verdict=result["summary"]["verdict"]):
                brief = build_owner_summary(result)
                self.assertIs(brief["local_follow_up"]["purchase_required"], False)
                self.assertIs(brief["workflow_follow_up"]["assessment_optional"], True)
                self.assertTrue(brief["local_follow_up"]["actions"])
                self.assertEqual(brief["evidence_gap_count"], result["summary"]["evidence_gap_count"])
                for rendered in (render_owner_html(result), render_html(result)):
                    self.assertIn("Continue with the free checks", rendered)
                    self.assertIn("Validate one actual workflow", rendered)
                    self.assertIn("No purchase required", rendered)

    def test_unknown_baseline_owner_summary_identifies_before_wrapper(self):
        result = compare_policy(lambda _: None, decide, "before", "after")
        brief = build_owner_summary(result)
        self.assertEqual(brief["priority_finding"]["policy_role"], "before")
        self.assertIn("before wrapper", brief["next_step"])
        self.assertEqual(brief["verdict"], "INCONCLUSIVE")

    def test_three_file_bundle_is_deterministic_and_keeps_complete_brief(self):
        result = run_demo("lost-response")
        with TemporaryDirectory() as temp:
            out = Path(temp)
            write_report(result, out)
            first = {name: (out / name).read_bytes() for name in ("report.html", "report.json", "owner-summary.html")}
            write_report(result, out)
            self.assertEqual(first, {name: (out / name).read_bytes() for name in first})
            stored = json.loads(first["report.json"])
            self.assertEqual(stored["owner_summary"], build_owner_summary(result))
            self.assertNotIn("owner_summary", result)

    def test_trace_brief_retains_priority_scope_and_limits(self):
        result = run_demo("lost-response")
        brief = build_owner_summary(result)
        self.assertEqual(brief["verdict"], result["summary"]["verdict"])
        self.assertIn("event_id", brief["priority_finding"])
        self.assertEqual(brief["declared_routes"], result["scope"]["routes"])
        self.assertEqual(brief["input_digest"], result["input_digest"])
        self.assertTrue(brief["assessment"]["optional"])

    def test_empty_demo_and_clean_policy_are_not_presented_as_customer_protection(self):
        for result in (run_demo(), compare_policy(decide, decide, "before", "after")):
            with self.subTest(kind=result["kind"]):
                brief = build_owner_summary(result)
                self.assertIn("synthetic", brief["scope_statement"])
                self.assertIn("Production protection is not established", " ".join(brief["limits"]))

    def test_owner_brief_escapes_labels_and_callback_names_without_remote_assets(self):
        result = run_demo("lost-response")
        result["workflow_name"] = '<script>alert("x")</script>'
        result["scope"]["routes"][0]["label"] = '<img src="https://example.invalid/pixel">'
        rendered = render_owner_html(result)
        self.assertIn("&lt;script&gt;", rendered)
        for tag in ("<script", "<img", "<link", "<iframe"):
            self.assertNotIn(tag, rendered)
        self.assertIn("Content-Security-Policy", rendered)

    def test_full_comparison_escapes_policy_names_and_exposes_keyboard_region(self):
        result = compare_policy(decide, decide, '<script>before</script>', "after")
        rendered = render_html(result)
        self.assertNotIn("<script", rendered)
        self.assertIn('aria-label="Before and after policy comparison"', rendered)
        self.assertIn('tabindex="0"', rendered)

    def test_owner_summary_cannot_overwrite_workflow_input(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "owner-summary.html"
            path.write_text("original input", encoding="utf-8")
            with self.assertRaises(InputError):
                write_report(run_demo(), Path(temp), path)
            self.assertEqual(path.read_text(encoding="utf-8"), "original input")

    def test_owner_summary_symlink_is_rejected_before_other_reports_are_replaced(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "report.html").write_text("previous report", encoding="utf-8")
            original = out / "original.html"
            original.write_text("original", encoding="utf-8")
            try:
                (out / "owner-summary.html").symlink_to(original)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks unavailable")
            with self.assertRaises(InputError):
                write_report(run_demo(), out)
            self.assertEqual((out / "report.html").read_text(encoding="utf-8"), "previous report")
            self.assertEqual(original.read_text(encoding="utf-8"), "original")

    def test_failure_installing_owner_summary_rolls_back_the_entire_bundle(self):
        for existing in (True, False):
            with self.subTest(existing=existing), TemporaryDirectory() as temp:
                out = Path(temp)
                targets = [out / name for name in ("report.html", "report.json", "owner-summary.html")]
                if existing:
                    for target in targets:
                        target.write_text("previous " + target.name, encoding="utf-8")
                replace = os.replace
                def fail_owner(source, target):
                    if Path(source).name == "owner-summary.html" and Path(target) == targets[2]:
                        raise OSError("simulated final write failure")
                    return replace(source, target)
                with patch("payment_control_lab.report.os.replace", side_effect=fail_owner), self.assertRaises(InputError):
                    write_report(run_demo(), out)
                for target in targets:
                    if existing:
                        self.assertEqual(target.read_text(encoding="utf-8"), "previous " + target.name)
                    else:
                        self.assertFalse(target.exists())
