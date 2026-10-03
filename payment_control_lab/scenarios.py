# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
from importlib.resources import files

from .input import InputError, parse_json
from .review import base_result, review_workflow


def scenario_index() -> list[dict]:
    return parse_json(files("payment_control_lab").joinpath("data/scenarios.json").read_text("utf-8"))


def run_demo(case_id: str | None = None) -> dict:
    cases = scenario_index()
    if case_id:
        cases = [c for c in cases if c["case_id"] == case_id]
        if not cases:
            raise InputError("Unknown demo case; use the list command to see supported cases.")
    reports = []
    for case in cases:
        trace = parse_json(files("payment_control_lab").joinpath("data").joinpath(case["resource"]).read_text("utf-8"))
        report = review_workflow(trace)
        report.update(case_id=case["case_id"], question=case["question"], expected_verdict=case["expected_verdict"])
        reports.append(report)
    if case_id:
        return reports[0]
    result = base_result("demo_suite", "Payment fallback and recovery", "synthetic")
    result["cases"] = reports
    result["summary"] = {
        "verdict": "SYNTHETIC_DEMO",
        "case_count": len(reports),
        "diagnoses_reproduced": sum(r["summary"]["verdict"] == r["expected_verdict"] for r in reports),
        "finding_count": sum(r["summary"]["finding_count"] for r in reports),
        "evidence_gap_count": sum(r["summary"]["evidence_gap_count"] for r in reports),
    }
    result["limitations"].insert(0, "The demo intentionally includes gaps, held replacements, and incomplete evidence. Reproducing its expected diagnoses does not establish that any real payment workflow is protected.")
    return result
