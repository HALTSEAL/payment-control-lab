# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Stateless example for the lab's explicit synthetic contexts only.

No evidence verification, authority state, concurrency, signing, or execution.
This is not HALTSEAL's production control implementation.
"""


def decide(context):
    proposal, obligation = context["proposal"], context["obligation"]
    if any(proposal[k] != obligation[k] for k in ("obligation_id", "amount_minor", "currency", "payee_ref")):
        return "REFUSE"
    if not context["fresh_decision"] or not context["approval_matches_proposal"]:
        return "REFUSE"
    matching = [a for a in context["prior_attempts"] if a["obligation_id"] == proposal["obligation_id"]]
    if any(a["outcome"] == "completed" for a in matching):
        return "REFUSE"
    if not context["declared_coverage_complete"]:
        return "HOLD"
    if any(a["outcome"] != "closed_no_effect" or not a["evidence_final"] or a["evidence_origin"] not in {"provider", "bank"} for a in matching):
        return "HOLD"
    return "ACCEPT"
