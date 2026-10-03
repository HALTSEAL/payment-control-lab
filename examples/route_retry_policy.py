# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Intentionally limited per-route logic, used to demonstrate fixture mismatches.

This is synthetic teaching code. Never connect it to payment execution.
"""


def decide(context):
    route = context["proposal"]["route_id"]
    if any(a["route_id"] == route and a["outcome"] == "unknown" for a in context["prior_attempts"]):
        return "HOLD"
    return "ACCEPT"
