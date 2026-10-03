# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
import copy
import json
import unittest
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from payment_control_lab.input import InputError, MAX_INPUT_BYTES, load_workflow, parse_json, validate_workflow
from payment_control_lab.review import review_workflow
from payment_control_lab.scenarios import run_demo, scenario_index


def fixture(name="lost-response"):
    return parse_json(files("payment_control_lab").joinpath(f"data/traces/{name}.json").read_text("utf-8"))


def codes(report):
    return {f["code"] for f in report["findings"]}


class TraceReviewTests(unittest.TestCase):
    def test_all_manually_authored_trace_expectations(self):
        for case in scenario_index():
            with self.subTest(case=case["case_id"]):
                report = run_demo(case["case_id"])
                self.assertEqual(report["summary"]["verdict"], case["expected_verdict"])

    def test_lost_response_identifies_actual_release_not_just_approval(self):
        report = review_workflow(fixture())
        self.assertIn("RELEASE_WHILE_UNRESOLVED", codes(report))
        release = next(f for f in report["findings"] if f["code"] == "RELEASE_WHILE_UNRESOLVED")
        self.assertEqual(release["predecessor_attempts"], ["attempt-a"])
        self.assertEqual(release["route_id"], "processor-b")

    def test_nonfinal_failure_does_not_close_original(self):
        self.assertIn("RELEASE_WHILE_UNRESOLVED", codes(review_workflow(fixture("nonfinal-failure"))))

    def test_held_replacement_is_not_reported_as_a_release(self):
        report = review_workflow(fixture("held-backup"))
        self.assertEqual(report["summary"]["finding_count"], 0)
        self.assertEqual(len(report["attempt_summary"]), 1)

    def test_final_provider_closure_allows_fresh_exact_replacement_in_trace(self):
        report = review_workflow(fixture("final-closure"))
        self.assertEqual(report["summary"]["verdict"], "NO_FINDING_IN_TRACE")

    def test_nonfinal_closure_claim_keeps_original_unresolved(self):
        trace = fixture("final-closure")
        trace["events"][2]["evidence"]["final"] = False
        report = review_workflow(trace)
        self.assertIn("FINAL_EVIDENCE_NOT_ESTABLISHED", codes(report))
        self.assertIn("RELEASE_WHILE_UNRESOLVED", codes(report))

    def test_missing_final_evidence_keeps_original_unresolved(self):
        trace = fixture("final-closure")
        trace["events"][2].pop("evidence")
        self.assertIn("RELEASE_WHILE_UNRESOLVED", codes(review_workflow(trace)))

    def test_operator_note_does_not_restore_permission_in_trace(self):
        report = review_workflow(fixture("operator-closure"))
        self.assertIn("RELEASE_WHILE_UNRESOLVED", codes(report))
        self.assertGreater(report["summary"]["evidence_gap_count"], 0)

    def test_synthetic_final_evidence_is_not_accepted_as_history_evidence(self):
        trace = fixture("final-closure")
        trace["events"][2]["evidence"]["origin"] = "synthetic"
        self.assertEqual(review_workflow(trace)["summary"]["verdict"], "NO_FINDING_IN_TRACE")
        trace["source_type"] = "redacted_history"
        self.assertIn("FINAL_EVIDENCE_NOT_ESTABLISHED", codes(review_workflow(trace)))

    def test_bank_final_evidence_is_supported_as_an_operator_claim(self):
        trace = fixture("final-closure")
        trace["events"][2]["evidence"]["origin"] = "bank"
        self.assertEqual(review_workflow(trace)["summary"]["verdict"], "NO_FINDING_IN_TRACE")

    def test_completed_obligation_cannot_be_released_again_without_finding(self):
        self.assertIn("RELEASE_AFTER_COMPLETION", codes(review_workflow(fixture("completed-repaid"))))

    def test_route_change_is_exactly_identified(self):
        report = review_workflow(fixture("route-changed"))
        finding = next(f for f in report["findings"] if f["code"] == "APPROVAL_ACTION_CHANGED")
        self.assertEqual(finding["changed_fields"], ["route_id"])
        self.assertEqual(finding["expected_action"]["route_id"], "processor-b")
        self.assertEqual(finding["recorded_action"]["route_id"], "bank-portal")
        self.assertEqual(report["timeline"][1]["record"]["action"]["route_id"], "bank-portal")

    def test_currency_change_is_detected(self):
        trace = fixture("amount-changed")
        trace["events"][1]["action"]["amount_minor"] = 125000
        trace["events"][1]["action"]["currency"] = "EUR"
        self.assertIn("APPROVAL_ACTION_CHANGED", codes(review_workflow(trace)))

    def test_refusing_a_changed_proposal_does_not_create_a_control_finding(self):
        trace = fixture("held-backup")
        trace["events"][-1]["decision"] = "REFUSE"
        trace["events"][-1]["action"]["amount_minor"] += 1
        self.assertEqual(review_workflow(trace)["summary"]["finding_count"], 0)

    def test_release_against_hold_and_refuse_is_detected(self):
        for decision in ("HOLD", "REFUSE"):
            with self.subTest(decision=decision):
                trace = fixture("route-changed")
                trace["events"][0]["decision"] = decision
                trace["events"][1]["action"] = copy.deepcopy(trace["events"][0]["action"])
                self.assertIn("RELEASE_AGAINST_DECISION", codes(review_workflow(trace)))

    def test_decision_before_closure_is_not_mistaken_for_fresh_validation(self):
        trace = fixture("final-closure")
        trace["events"][2], trace["events"][3] = trace["events"][3], trace["events"][2]
        for index, event in enumerate(trace["events"]):
            event["at"] = f"2026-01-01T12:00:0{index}Z"
        self.assertIn("ACCEPT_WHILE_UNRESOLVED", codes(review_workflow(trace)))

    def test_two_approvals_before_release_are_caught_at_execution(self):
        self.assertIn("RELEASE_WHILE_UNRESOLVED", codes(review_workflow(fixture("two-approvals"))))

    def test_approval_before_original_release_is_stale_after_final_closure(self):
        trace = fixture("final-closure")
        original_decision, original_release, closure, replacement_decision, replacement_release = trace["events"]
        trace["events"] = [original_decision, replacement_decision, original_release, closure, replacement_release]
        for index, event in enumerate(trace["events"]):
            event["at"] = f"2026-01-01T12:00:0{index}Z"
        report = review_workflow(trace)
        self.assertIn("DECISION_PREDATES_CLOSURE", codes(report))
        self.assertNotIn("RELEASE_WHILE_UNRESOLVED", codes(report))
        self.assertEqual(report["summary"]["verdict"], "CONTROL_GAP_OBSERVED")

    def test_duplicate_closure_after_fresh_decision_does_not_invalidate_it(self):
        trace = fixture("final-closure")
        duplicate = copy.deepcopy(trace["events"][2])
        duplicate["event_id"] = "duplicate-closure"
        trace["events"].insert(4, duplicate)
        for index, event in enumerate(trace["events"]):
            event["at"] = f"2026-01-01T12:00:0{index}Z"
        self.assertEqual(review_workflow(trace)["summary"]["verdict"], "NO_FINDING_IN_TRACE")

    def test_declared_obligation_without_records_is_an_evidence_gap(self):
        trace = fixture("held-backup")
        trace["obligations"].append({**trace["obligations"][0], "obligation_id": "invoice-unobserved"})
        report = review_workflow(trace)
        self.assertEqual(report["summary"]["verdict"], "INCONCLUSIVE")
        finding = next(f for f in report["findings"] if f["code"] == "OBLIGATION_NOT_OBSERVED")
        self.assertEqual(finding["obligation_id"], "invoice-unobserved")

    def test_repeated_final_closure_does_not_hide_an_active_replacement(self):
        trace = fixture("final-closure")
        closure = copy.deepcopy(trace["events"][2])
        closure.update(event_id="repeat-closure", at="2026-01-01T12:00:05Z")
        decision = copy.deepcopy(trace["events"][3])
        decision.update(event_id="third-decision", decision_id="decision-c", at="2026-01-01T12:00:06Z")
        decision["action"].update(attempt_id="attempt-c", route_id="bank-portal")
        release = {"type": "release", "event_id": "third-release", "at": "2026-01-01T12:00:07Z", "decision_id": "decision-c", "action": copy.deepcopy(decision["action"])}
        trace["events"].extend([closure, decision, release])
        self.assertIn("RELEASE_WHILE_UNRESOLVED", codes(review_workflow(trace)))

    def test_conflicting_terminal_evidence_is_inconclusive(self):
        self.assertEqual(review_workflow(fixture("conflicting-outcomes"))["summary"]["verdict"], "INCONCLUSIVE")

    def test_outcome_before_captured_release_is_not_silently_ignored(self):
        trace = fixture("held-backup")
        trace["events"].insert(0, {"type": "outcome", "event_id": "missing-first", "at": "2026-01-01T11:00:00Z", "attempt_id": "absent-attempt", "outcome": "completed"})
        self.assertIn("RELEASE_NOT_CAPTURED", codes(review_workflow(trace)))

    def test_missing_manual_path_prevents_no_finding_verdict(self):
        self.assertEqual(review_workflow(fixture("unobserved-portal"))["summary"]["verdict"], "INCONCLUSIVE")

    def test_missing_decision_is_an_evidence_gap_not_an_assertion_of_bypass(self):
        report = review_workflow(fixture("missing-decision"))
        self.assertEqual(report["summary"]["verdict"], "INCONCLUSIVE")
        self.assertIn("DECISION_NOT_CAPTURED", codes(report))
        self.assertNotIn("RELEASE_AGAINST_DECISION", codes(report))

    def test_separate_obligations_are_not_conflated_by_equal_amount_and_payee(self):
        self.assertEqual(review_workflow(fixture("independent-obligations"))["summary"]["finding_count"], 0)

    def test_reused_decision_is_reported_after_reliable_closure(self):
        self.assertIn("DECISION_REUSED", codes(review_workflow(fixture("reused-decision"))))

    def test_later_refusal_cannot_be_hidden_by_linking_an_older_accept(self):
        trace = fixture("route-changed")
        trace["events"][1]["action"] = copy.deepcopy(trace["events"][0]["action"])
        refusal = copy.deepcopy(trace["events"][0])
        refusal.update(event_id="later-refusal", decision_id="refused-now", decision="REFUSE", at="2026-01-01T12:00:01Z")
        trace["events"][1]["at"] = "2026-01-01T12:00:02Z"
        trace["events"].insert(1, refusal)
        self.assertIn("DECISION_SUPERSEDED", codes(review_workflow(trace)))

    def test_digest_and_diagnosis_are_deterministic(self):
        a = fixture()
        self.assertEqual(review_workflow(a), review_workflow(copy.deepcopy(a)))
        reversed_keys = {k: a[k] for k in reversed(a)}
        self.assertEqual(review_workflow(a)["input_digest"], review_workflow(reversed_keys)["input_digest"])


class InputTests(unittest.TestCase):
    def assert_invalid(self, mutate):
        data = fixture()
        mutate(data)
        with self.assertRaises(InputError):
            validate_workflow(data)

    def test_duplicate_json_keys(self):
        with self.assertRaises(InputError):
            parse_json('{"source_type":"synthetic","source_type":"redacted_history"}')

    def test_nonfinite_numbers(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(InputError):
                parse_json(value)

    def test_boolean_is_not_money(self):
        self.assert_invalid(lambda d: d["obligations"][0].update(amount_minor=True))

    def test_negative_zero_and_floating_money(self):
        for value in (-1, 0, 1.5, 9007199254740992):
            with self.subTest(value=value):
                self.assert_invalid(lambda d: d["obligations"][0].update(amount_minor=value))

    def test_schema_version(self):
        self.assert_invalid(lambda d: d.update(schema_version="future"))

    def test_unknown_sensitive_fields_are_rejected(self):
        self.assert_invalid(lambda d: d.update(account_number="not-allowed"))
        self.assert_invalid(lambda d: d["events"][0]["action"].update(email="not-allowed"))

    def test_missing_required_fields(self):
        self.assert_invalid(lambda d: d.pop("source_type"))

    def test_unknown_obligation_and_route(self):
        for key in ("route_id", "obligation_id"):
            with self.subTest(key=key):
                self.assert_invalid(lambda d: d["events"][0]["action"].update({key: "undeclared"}))

    def test_naive_and_invalid_dates(self):
        for stamp in ("2026-01-01T12:00:00", "2026-02-30T12:00:00Z"):
            with self.subTest(stamp=stamp):
                self.assert_invalid(lambda d: d["events"][0].update(at=stamp))

    def test_out_of_order_records_are_not_sorted_into_a_pass(self):
        self.assert_invalid(lambda d: d["events"][-1].update(at="2025-01-01T00:00:00Z"))

    def test_timezone_offsets_compare_by_instant(self):
        d = fixture()
        d["events"][0]["at"] = "2026-01-01T07:00:00-05:00"
        validate_workflow(d)

    def test_duplicate_aliases(self):
        self.assert_invalid(lambda d: d["routes"].append(copy.deepcopy(d["routes"][0])))
        self.assert_invalid(lambda d: d["obligations"].append(copy.deepcopy(d["obligations"][0])))
        self.assert_invalid(lambda d: d["events"][-1].update(event_id=d["events"][0]["event_id"]))
        self.assert_invalid(lambda d: d["events"][3].update(decision_id=d["events"][0]["decision_id"]))

    def test_reused_attempt_alias_is_rejected_as_ambiguous(self):
        self.assert_invalid(lambda d: d["events"][-1]["action"].update(attempt_id="attempt-a"))

    def test_control_characters_in_labels(self):
        self.assert_invalid(lambda d: d.update(workflow_name="line\nbreak"))

    def test_invalid_unicode_and_misleading_formatting_are_rejected(self):
        for text in ("\ud800", "\udfff", "\u0085", "\u202eACCEPT", "\u2066hidden"):
            with self.subTest(text=ascii(text)):
                self.assert_invalid(lambda d: d.update(workflow_name=text))

    def test_multilingual_and_supplementary_unicode_labels_remain_supported(self):
        trace = fixture("held-backup")
        trace["workflow_name"] = "지급 검토 · مراجعة الدفع · \U0001f30e"
        trace["routes"][0]["label"] = "원래 경로"
        validate_workflow(trace)
        self.assertEqual(review_workflow(trace)["workflow_name"], trace["workflow_name"])

    def test_timestamp_contract_rejects_normalized_invalid_offsets(self):
        for stamp in ("2026-01-01T12:00:00+00:99", "2026-01-01T12:00:00+24:00", "2026-01-01 12:00:00Z", "2026-01-01T12:00:00+0100"):
            with self.subTest(stamp=stamp):
                self.assert_invalid(lambda d: d["events"][0].update(at=stamp))

    def test_fractional_seconds_and_explicit_timezone_are_supported(self):
        trace = fixture()
        trace["events"][0]["at"] = "2026-01-01T11:59:59.123456+00:00"
        validate_workflow(trace)

    def test_empty_trace_is_inconclusive(self):
        d = fixture()
        d["events"] = []
        self.assertEqual(review_workflow(d)["summary"]["verdict"], "INCONCLUSIVE")

    def test_file_limits_and_encoding(self):
        with TemporaryDirectory() as temp:
            p = Path(temp) / "input.json"
            for payload in (b"x" * (MAX_INPUT_BYTES + 1), b"\xff"):
                p.write_bytes(payload)
                with self.assertRaises(InputError):
                    load_workflow(p)

    def test_deep_json_returns_input_error(self):
        with self.assertRaises(InputError):
            parse_json("[" * 2000 + "0" + "]" * 2000)

    def test_published_schema_matches_bundled_schema(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / "schemas/workflow.schema.json").read_text(encoding="utf-8")), json.loads(files("payment_control_lab").joinpath("data/workflow.schema.json").read_text(encoding="utf-8")))

    def test_schema_patterns_cover_the_entire_value_for_external_validators(self):
        schema = json.loads(files("payment_control_lab").joinpath("data/workflow.schema.json").read_text(encoding="utf-8"))
        def inspect(spec):
            if isinstance(spec, dict):
                if "pattern" in spec:
                    self.assertTrue(spec["pattern"].startswith("^") and spec["pattern"].endswith("$"))
                for value in spec.values():
                    inspect(value)
            elif isinstance(spec, list):
                for value in spec:
                    inspect(value)
        inspect(schema)


if __name__ == "__main__":
    unittest.main()
