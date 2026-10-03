# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Independent synthetic expectations for a trusted, locally supplied function."""

from __future__ import annotations

import copy
import importlib
import re
import sys
from importlib.resources import files
from pathlib import Path

from .input import InputError, digest, parse_json
from .review import base_result, summarize


def load_policy(spec: str):
    if len(spec) > 200 or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", spec):
        raise InputError("Policy must have the form importable.module:function.")
    module_name, function_name = spec.split(":")
    # check-policy explicitly runs trusted user code. Allow a module in the
    # working directory for both checkout and installed console-script use.
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    try:
        policy = getattr(importlib.import_module(module_name), function_name)
    except (Exception, SystemExit) as exc:
        raise InputError(f"Cannot load the local policy function ({type(exc).__name__}).") from None
    if not callable(policy):
        raise InputError("The selected policy attribute is not callable.")
    return policy


def check_policy(policy, name: str) -> dict:
    challenges = parse_json(files("payment_control_lab").joinpath("data/policy-challenges.json").read_text("utf-8"))
    return _check_policy(policy, name, challenges)


def _check_policy(policy, name: str, challenges: list[dict]) -> dict:
    result = base_result("policy_challenge", f"Local function: {name}", "synthetic")
    result["input_digest"] = digest({"challenges": challenges})
    result["limitations"].insert(0, "These are independently authored synthetic expectations. Matching them does not prove production behavior, concurrency safety, evidence authenticity, or full coverage.")
    result["policy_cases"] = []
    for case in challenges:
        row = {"case_id": case["case_id"], "title": case["title"], "allowed_decisions": case["allowed_decisions"]}
        try:
            observed = policy(copy.deepcopy(case["context"]))
            if type(observed) is not str or observed not in {"ACCEPT", "HOLD", "REFUSE"}:
                raise ValueError("Invalid decision value")
        except (Exception, SystemExit) as exc:
            row.update(observed_decision=None, status="INCONCLUSIVE", error_type=type(exc).__name__)
            result["findings"].append({"finding_id": f"F{len(result['findings']) + 1:03d}", "code": "POLICY_ERROR", "category": "evidence_gap", "case_id": case["case_id"], "summary": f"The function did not return a supported decision for {case['title']}.", "next_step": "Check the local callable and return ACCEPT, HOLD, or REFUSE. Exception messages are omitted to avoid leaking data."})
        else:
            matched = observed in case["allowed_decisions"]
            row.update(observed_decision=observed, status="MATCH" if matched else "MISMATCH")
            if not matched:
                result["findings"].append({"finding_id": f"F{len(result['findings']) + 1:03d}", "code": "FIXTURE_MISMATCH", "category": "fixture_mismatch", "case_id": case["case_id"], "summary": f"The function returned {observed} for {case['title']}; the fixture expects {' or '.join(case['allowed_decisions'])}.", "next_step": "Review this case with the workflow owner. A mismatch can indicate unsafe acceptance or unnecessary refusal; it is not a recorded payment incident."})
        result["policy_cases"].append(row)
    return summarize(result)


def compare_policy(before_policy, after_policy, before_name: str, after_name: str) -> dict:
    """Compare two trusted functions against the same absolute fixture contract.

    A smaller mismatch count never cancels a regression or remaining mismatch.
    Unknown baseline behavior cannot establish an improvement.
    """
    challenges = parse_json(files("payment_control_lab").joinpath("data/policy-challenges.json").read_text("utf-8"))
    before = _check_policy(before_policy, before_name, challenges)
    after = _check_policy(after_policy, after_name, challenges)
    result = base_result("policy_comparison", f"Policy change: {before_name} to {after_name}", "synthetic")
    result["input_digest"] = after["input_digest"]
    result["limitations"] = list(after["limitations"])
    result["limitations"].insert(0, "Before and after functions are run sequentially on the same synthetic contexts. Use deterministic wrappers with isolated test state; this does not exercise live execution or distributed concurrency.")
    result["policy_cases"] = after["policy_cases"]
    result["findings"] = [dict(f, policy_role="after") for f in after["findings"]]
    for finding in before["findings"]:
        if finding["category"] == "evidence_gap":
            result["findings"].append(dict(
                finding, code="BASELINE_POLICY_ERROR", policy_role="before",
                summary="The before function did not return a supported decision; this change cannot be fully compared.",
                next_step="Repair the before wrapper or its return mapping and rerun the comparison. A matching candidate does not resolve an unknown baseline.",
            ))
    for index, finding in enumerate(result["findings"], 1):
        finding["finding_id"] = f"F{index:03d}"
    rows = []
    for prior, current in zip(before["policy_cases"], after["policy_cases"]):
        left, right = prior["status"], current["status"]
        if right == "INCONCLUSIVE":
            transition = "UNRESOLVED" if left == "INCONCLUSIVE" else "NEW_UNCERTAINTY"
        elif left == "INCONCLUSIVE":
            transition = "BASELINE_UNKNOWN"
        elif left == "MISMATCH" and right == "MATCH":
            transition = "IMPROVED"
        elif left == "MATCH" and right == "MISMATCH":
            transition = "REGRESSED"
        else:
            transition = "UNCHANGED_MATCH" if right == "MATCH" else "STILL_MISMATCHED"
        row = {
            "case_id": current["case_id"], "title": current["title"],
            "allowed_decisions": current["allowed_decisions"],
            "before_decision": prior["observed_decision"], "after_decision": current["observed_decision"],
            "before_status": left, "after_status": right, "transition": transition,
        }
        for role, case in (("before", prior), ("after", current)):
            if "error_type" in case:
                row[f"{role}_error_type"] = case["error_type"]
        rows.append(row)
    result["comparison_cases"] = rows
    result["comparison"] = {
        "before_policy": before_name, "after_policy": after_name,
        "before_verdict": before["summary"]["verdict"], "after_verdict": after["summary"]["verdict"],
        "case_count": len(rows),
        "improved_count": sum(r["transition"] == "IMPROVED" for r in rows),
        "regressed_count": sum(r["transition"] == "REGRESSED" for r in rows),
        "uncertain_count": sum("INCONCLUSIVE" in {r["before_status"], r["after_status"]} for r in rows),
        "after_mismatch_count": after["summary"]["finding_count"],
    }
    return summarize(result)
