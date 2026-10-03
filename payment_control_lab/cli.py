# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Small offline CLI with explicit diagnostic exit codes."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .challenges import check_policy, compare_policy, load_policy
from .input import InputError, load_workflow, parse_json
from .report import LABELS, write_report
from .review import review_workflow
from .scenarios import run_demo, scenario_index


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="payment-control-lab", description="Review payment fallback records locally. No payment authority or network access in the bundled diagnostics.")
    root.add_argument("--version", action="version", version=f"payment-control-lab {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Reproduce the bundled synthetic traces")
    demo.add_argument("--case", help="Review one case from the list command")
    demo.add_argument("--out", type=Path, default=Path("out/demo"))
    review = commands.add_parser("review", help="Review your supplied, redacted workflow records")
    review.add_argument("input", type=Path)
    review.add_argument("--out", type=Path, default=Path("out/review"))
    policy = commands.add_parser("check-policy", help="Compare a trusted local function with synthetic expectations")
    policy.add_argument("policy", help="importable.module:function (trusted local Python code)")
    policy.add_argument("--out", type=Path, default=Path("out/policy"))
    compare = commands.add_parser("compare-policy", help="Compare before/after trusted functions against the same synthetic expectations")
    compare.add_argument("before", help="before.module:function (trusted local Python code)")
    compare.add_argument("after", help="after.module:function (trusted local Python code)")
    compare.add_argument("--out", type=Path, default=Path("out/comparison"))
    for command in (review, policy, compare):
        command.add_argument("--ci-mode", choices=("gate", "report"), default="gate", help="gate preserves diagnostic exits; report makes findings/inconclusive results advisory, never input errors")
    template = commands.add_parser("template", help="Create an empty history template; never overwrites an existing file")
    template.add_argument("--out", type=Path, default=Path("workflow.json"))
    commands.add_parser("list", help="List the bundled synthetic trace cases")
    return root


def diagnostic_exit(result: dict) -> int:
    verdict = result["summary"]["verdict"]
    if verdict in {"CONTROL_GAP_OBSERVED", "EXPECTATIONS_NOT_MET"}:
        return 2
    if verdict == "INCONCLUSIVE":
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "list":
            for case in scenario_index():
                print(f"{case['case_id']:24} {case['title']}")
            return 0
        if args.command == "template":
            template = parse_json(files("payment_control_lab").joinpath("data/workflow-template.json").read_text("utf-8"))
            try:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                with args.out.open("x", encoding="utf-8") as stream:
                    stream.write(json.dumps(template, indent=2) + "\n")
            except FileExistsError:
                raise InputError("Template path already exists; choose another path.") from None
            except OSError:
                raise InputError("Cannot write the template; check the destination directory.") from None
            print(f"Template: {args.out}\nReplace the aliases and add redacted records. An empty trace is inconclusive.")
            return 0
        if args.command == "demo":
            result = run_demo(args.case)
        elif args.command == "review":
            result = review_workflow(load_workflow(args.input))
        elif args.command == "compare-policy":
            before = load_policy(args.before)
            after = load_policy(args.after)
            result = compare_policy(before, after, args.before, args.after)
        else:
            result = check_policy(load_policy(args.policy), args.policy)
        if args.command != "demo":
            code = diagnostic_exit(result)
            result["ci"] = {"mode": args.ci_mode, "diagnostic_exit_code": code, "process_exit_code": 0 if args.ci_mode == "report" else code}
        html_path, json_path = write_report(result, args.out, getattr(args, "input", None))
        summary = result["summary"]
        print(f"Payment Control Lab {__version__}\n{LABELS[summary['verdict']][0]}\nFindings: {summary['finding_count']} | Evidence gaps: {summary['evidence_gap_count']}\nHTML: {html_path}\nJSON: {json_path}\nOwner summary: {args.out / 'owner-summary.html'}")
        if args.command == "demo":
            reproduced = result["summary"].get("diagnoses_reproduced", int(result["summary"]["verdict"] == result.get("expected_verdict")))
            count = result["summary"].get("case_count", 1)
            print(f"Expected diagnoses reproduced: {reproduced}/{count}. Synthetic data; no payment authority.")
            # Demo success means the fixture diagnoses were reproduced, not that a
            # payment workflow passed a safety check. review/check-policy use 2/3.
            return 0 if reproduced == count else 1
        print(f"CI mode: {args.ci_mode} | Diagnostic exit: {result['ci']['diagnostic_exit_code']} | Process exit: {result['ci']['process_exit_code']}")
        return result["ci"]["process_exit_code"]
    except InputError as exc:
        print(f"Input/configuration error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
