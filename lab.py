#!/usr/bin/env python3
# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Run the lab directly from a checkout, without installing dependencies."""

from payment_control_lab.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
