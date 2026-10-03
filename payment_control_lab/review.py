# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Passive diagnostics of supplied records; never authorizes or executes a payment."""

from __future__ import annotations

import copy
from itertools import islice

from . import __version__
from .input import digest, validate_workflow

ACTION_FIELDS = ("obligation_id", "attempt_id", "route_id", "amount_minor", "currency", "payee_ref")
DETAIL_FIELDS = ("amount_minor", "currency", "payee_ref")


def base_result(kind: str, name: str, source_type: str) -> dict:
    return {
        "report_schema_version": "0.2",
        "tool_version": __version__,
        "kind": kind,
        "workflow_name": name,
        "source_type": source_type,
        "findings": [],
        "limitations": [
            "Only supplied records and declared routes are reviewed. Omitted obligations or routes cannot be discovered automatically.",
            "Evidence labels and obligation mapping are supplied by the operator. The lab does not authenticate provider or bank evidence.",
            "No payment is executed, blocked, signed, or authorized by this tool. No production readiness or certification is implied.",
        ],
    }


def summarize(result: dict) -> dict:
    gaps = sum(f["category"] != "evidence_gap" for f in result["findings"])
    evidence = sum(f["category"] == "evidence_gap" for f in result["findings"])
    if result["kind"] in {"policy_challenge", "policy_comparison"}:
        verdict = "EXPECTATIONS_NOT_MET" if gaps else "INCONCLUSIVE" if evidence else "EXPECTATIONS_MET"
    else:
        verdict = "CONTROL_GAP_OBSERVED" if gaps else "INCONCLUSIVE" if evidence else "NO_FINDING_IN_TRACE"
    result["summary"] = {"verdict": verdict, "finding_count": gaps, "evidence_gap_count": evidence}
    return result


def review_workflow(data: dict) -> dict:
    validate_workflow(data)
    result = base_result("trace_review", data["workflow_name"], data["source_type"])
    result["input_digest"] = digest(data)
    result["scope"] = {"routes": data["routes"], "obligations": data["obligations"], "event_count": len(data["events"])}
    result["timeline"] = []
    if data["source_type"] == "synthetic":
        result["limitations"].insert(0, "This is a synthetic trace. A reproduced scenario is not evidence of a real customer incident or production protection.")
    routes = {r["route_id"]: r for r in data["routes"]}
    obligations = {o["obligation_id"]: o for o in data["obligations"]}
    active = {key: {} for key in obligations}
    completed = {key: {} for key in obligations}
    attempts, decisions, latest_decisions, used_decisions = {}, {}, {}, set()
    decision_positions, last_closure = {}, {}

    def add(code: str, category: str, summary: str, next_step: str, event: dict | None = None, action: dict | None = None, **extra) -> None:
        finding = {"finding_id": f"F{len(result['findings']) + 1:03d}", "code": code, "category": category, "summary": summary, "next_step": next_step}
        if event:
            finding["event_id"] = event["event_id"]
        if action:
            finding.update({k: action[k] for k in ("obligation_id", "attempt_id", "route_id")})
        finding.update(extra)
        result["findings"].append(finding)

    for route in data["routes"]:
        if route["coverage"] == "unobserved":
            add("UNOBSERVED_ROUTE", "evidence_gap", f"No execution records are supplied for {route['label']}.", "Obtain redacted records or document how this path is governed before concluding coverage.", route_id=route["route_id"])
    if not data["events"]:
        add("NO_EVENTS", "evidence_gap", "The trace contains no observed events.", "Add decision, release, and outcome records for one real workflow.")
    else:
        observed_obligations = {e["action"]["obligation_id"] for e in data["events"] if "action" in e}
        for key in (key for key in obligations if key not in observed_obligations):
            add("OBLIGATION_NOT_OBSERVED", "evidence_gap", "A declared obligation has no decision or release records in this trace.", "Supply its redacted records or narrow the declared review scope.", obligation_id=key)

    def inspect_details(event: dict, action: dict) -> None:
        changed = [field for field in DETAIL_FIELDS if action[field] != obligations[action["obligation_id"]][field]]
        if changed:
            add("OBLIGATION_DETAILS_CHANGED", "control_gap", "The proposed or released payment differs from the declared obligation.", "Confirm the obligation mapping and obtain a decision for the exact amount, currency, and payee.", event, action, changed_fields=changed, expected_details={field: obligations[action["obligation_id"]][field] for field in changed}, recorded_details={field: action[field] for field in changed})

    def inspect_predecessor(event: dict, action: dict, prefix: str) -> None:
        key = action["obligation_id"]
        verb = "accepted" if prefix == "ACCEPT" else "released"
        if completed[key]:
            add(f"{prefix}_AFTER_COMPLETION", "control_gap", f"A replacement is {verb} after an earlier attempt for this obligation completed.", "Reconcile the completed attempt before approving or releasing another payment for the same obligation.", event, action, predecessor_attempts=list(islice(completed[key], 3)), predecessor_count=len(completed[key]))
        elif active[key]:
            add(f"{prefix}_WHILE_UNRESOLVED", "control_gap", f"A replacement is {verb} while an earlier attempt for this obligation remains unresolved.", "Keep the replacement on hold until reliable closure evidence is obtained, then validate the exact replacement again.", event, action, predecessor_attempts=list(islice(active[key], 3)), predecessor_count=len(active[key]))

    for position, event in enumerate(data["events"]):
        kind = event["type"]
        action = event.get("action")
        if action:
            if routes[action["route_id"]]["coverage"] != "captured":
                add("COVERAGE_CONTRADICTION", "evidence_gap", "A route labeled unobserved contains an action record.", "Reconcile the declared coverage with the supplied records.", event, action)
            if kind == "release" or (kind == "decision" and event["decision"] == "ACCEPT"):
                inspect_details(event, action)
        if kind == "decision":
            decisions[event["decision_id"]] = event
            latest_decisions[action["attempt_id"]] = event["decision_id"]
            decision_positions[event["decision_id"]] = position
            if event["decision"] == "ACCEPT":
                inspect_predecessor(event, action, "ACCEPT")
            detail = f"{event['decision']} recorded for {action['attempt_id']} via {action['route_id']}."
        elif kind == "release":
            inspect_predecessor(event, action, "RELEASE")
            decision_id = event.get("decision_id")
            decision = decisions.get(decision_id)
            if not decision:
                add("DECISION_NOT_CAPTURED", "evidence_gap", "No preceding decision record is linked to this release.", "Supply the preceding decision record. Missing logs are not proof that approval was absent.", event, action)
            else:
                if latest_decisions.get(action["attempt_id"]) not in {None, decision_id}:
                    add("DECISION_SUPERSEDED", "control_gap", "A release is linked to an older decision after a newer decision was recorded for the same attempt.", "Use the latest recorded decision and confirm that execution cannot rely on a superseded acceptance.", event, action)
                if decision["decision"] != "ACCEPT":
                    add("RELEASE_AGAINST_DECISION", "control_gap", "A release is recorded against a HOLD or REFUSE decision.", "Check whether the execution path bypasses the recorded decision.", event, action)
                changed = [field for field in ACTION_FIELDS if action[field] != decision["action"][field]]
                if changed:
                    add("APPROVAL_ACTION_CHANGED", "control_gap", "The released action differs from the action in its linked decision.", "Obtain a new decision for the exact proposed payment and route.", event, action, changed_fields=changed, expected_action=copy.deepcopy(decision["action"]), recorded_action=copy.deepcopy(action))
                if decision_id in used_decisions:
                    add("DECISION_REUSED", "control_gap", "One decision is linked to more than one distinct execution attempt.", "Check that each distinct execution receives its own current decision.", event, action)
                used_decisions.add(decision_id)
                closure = last_closure.get(action["obligation_id"])
                if decision["decision"] == "ACCEPT" and closure and decision_positions[decision_id] < closure["position"]:
                    add("DECISION_PREDATES_CLOSURE", "control_gap", "The replacement reuses a decision recorded before its predecessor's supported final closure.", "Record a fresh decision for the exact replacement after the predecessor's final closure.", event, action, decision_id=decision_id, closure_event_id=closure["event_id"], predecessor_attempts=[closure["attempt_id"]])
            attempts[action["attempt_id"]] = {"action": action, "status": "unknown"}
            active[action["obligation_id"]][action["attempt_id"]] = None
            detail = f"Release recorded for {action['attempt_id']} via {action['route_id']}."
        else:
            attempt_id, outcome = event["attempt_id"], event["outcome"]
            attempt = attempts.get(attempt_id)
            if attempt is None:
                add("RELEASE_NOT_CAPTURED", "evidence_gap", "An outcome has no preceding release record in the supplied trace.", "Supply the missing execution record and confirm the event ordering.", event, attempt_id=attempt_id)
            else:
                action = attempt["action"]
                key = action["obligation_id"]
                evidence = event.get("evidence", {})
                trusted_final = evidence.get("final") is True and (evidence.get("origin") in {"provider", "bank"} or (data["source_type"] == "synthetic" and evidence.get("origin") == "synthetic"))
                prior = attempt["status"]
                if prior in {"completed", "closed_no_effect", "conflicted"} and outcome != prior:
                    add("CONFLICTING_OUTCOME", "evidence_gap", "A later outcome contradicts or regresses a previously recorded terminal outcome.", "Resolve the conflicting evidence; do not rely on the trace as proof that a prior attempt cannot create an effect.", event, action)
                    attempt["status"] = "conflicted"
                    active[key][attempt_id] = None
                elif outcome in {"completed", "closed_no_effect"}:
                    if not trusted_final:
                        add("FINAL_EVIDENCE_NOT_ESTABLISHED", "evidence_gap", "A terminal outcome is claimed without supported final evidence in the supplied record.", "Obtain provider or bank final evidence and verify its authority outside the lab.", event, action)
                    else:
                        attempt["status"] = outcome
                        active[key].pop(attempt_id, None)
                        if outcome == "completed":
                            completed[key][attempt_id] = None
                        elif prior != "closed_no_effect":
                            # A duplicate closure record must not make an already
                            # fresh decision appear stale.
                            last_closure[key] = {"position": position, "event_id": event["event_id"], "attempt_id": attempt_id}
                # unknown and failed_nonfinal never close an unresolved attempt.
            detail = f"{outcome} recorded for {attempt_id}."
        result["timeline"].append({"event_id": event["event_id"], "at": event["at"], "type": kind, "detail": detail, "record": copy.deepcopy(event)})

    result["attempt_summary"] = [{"attempt_id": key, "obligation_id": value["action"]["obligation_id"], "route_id": value["action"]["route_id"], "replay_status": value["status"]} for key, value in attempts.items()]
    return summarize(result)
