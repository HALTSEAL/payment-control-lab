# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Copy into YOUR repository as payment_policy_adapter.py, then bind your code.

The lab supplies synthetic contexts. Replace this body with a call to your
existing decision logic and explicit mapping to ACCEPT, HOLD, or REFUSE.
Mock dependencies and reset test state inside your wrapper. Never call a
payment release function or use production credentials here.

An unconfigured adapter is deliberately inconclusive, not a passing example.
See docs/ADOPT_IN_CI.md and docs/POLICY_CHECKS.md for the complete contract.
"""


def decide(context):
    raise NotImplementedError("Bind a trusted local decision function before using this adapter.")
