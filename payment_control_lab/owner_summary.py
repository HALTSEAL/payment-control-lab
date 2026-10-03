# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""A bounded workflow-owner brief, derived from the same diagnostic result."""

from __future__ import annotations

import html
from typing import Any

ASSESSMENT_URL = "https://haltseal.com/evaluate/?source=payment-control-lab#contact"

VERDICT_LABELS = {
    "CONTROL_GAP_OBSERVED": ("Control gap observed", "gap"),
    "INCONCLUSIVE": ("More evidence needed", "unknown"),
    "NO_FINDING_IN_TRACE": ("No finding in this trace", "clear"),
    "EXPECTATIONS_NOT_MET": ("Fixture expectations not met", "gap"),
    "EXPECTATIONS_MET": ("Fixture expectations met", "clear"),
    "SYNTHETIC_DEMO": ("Synthetic demonstration", "demo"),
}


def build_owner_summary(result: dict) -> dict[str, Any]:
    summary = result["summary"]
    kind = result["kind"]
    policy = kind in {"policy_challenge", "policy_comparison"}
    findings = result["findings"]
    priority = next((f for f in findings if f["category"] != "evidence_gap"), None)
    priority = priority or next(iter(findings), None)
    scope = result.get("scope", {})
    if priority:
        requested = "Review the finding and agree the next change with the workflow owner."
        next_step = priority["next_step"]
    elif kind == "demo_suite":
        requested = "Choose one actual workflow and identify its original and replacement paths."
        next_step = "Run a trusted local decision function or review redacted records from that workflow."
    elif policy:
        requested = "Retain the checks and establish what still needs validation in the actual workflow."
        next_step = "Confirm event capture, evidence authority, unobserved paths, and execution behavior separately."
    else:
        requested = "Confirm the review scope before drawing a conclusion about the actual workflow."
        next_step = "Keep the declared paths, obligation mapping, and evidence limits attached to this result."
    if kind == "demo_suite":
        source_scope = f"{summary['case_count']} synthetic traces; no customer workflow has been inspected."
    elif policy:
        source_scope = f"{len(result['policy_cases'])} synthetic contexts; the callable is not an execution-flow test."
    else:
        source_scope = f"{len(scope['obligations'])} mapped obligations, {len(scope['routes'])} declared paths, {scope['event_count']} supplied events."
    if kind == "demo_suite":
        local_actions = ["Connect your existing local decision function or review redacted records for one workflow."]
    elif policy:
        local_actions = []
        if summary["finding_count"]:
            local_actions.append("Inspect each candidate mismatch, fix the decision logic or its wrapper, and rerun these free checks. Include valid payments as well as risky replacements.")
        if summary["evidence_gap_count"]:
            local_actions.append("Resolve unsupported returns or callback errors, including the baseline, before claiming a complete comparison.")
        if not local_actions:
            local_actions.append("Keep these sixteen checks in CI when retry, route, approval, or evidence logic changes.")
    else:
        local_actions = ["Inspect the referenced events, correct code or record mapping where appropriate, and rerun the free record review." if summary["finding_count"] else "Retain this result with its declared paths and evidence limits."]
        if summary["evidence_gap_count"]:
            local_actions.append("Add missing records or reconcile conflicting outcomes; a successful advisory run does not resolve an evidence gap.")
    brief = {
        "schema_version": "0.1", "workflow_name": result["workflow_name"],
        "source_type": result["source_type"], "result_kind": kind,
        "verdict": summary["verdict"], "finding_count": summary["finding_count"],
        "finding_label": "Fixture mismatches" if policy else "Recorded findings",
        "evidence_gap_count": summary["evidence_gap_count"],
        "scope_statement": source_scope, "declared_routes": scope.get("routes", []),
        "decision_requested": requested, "next_step": next_step,
        "priority_finding": {k: priority[k] for k in ("code", "summary", "policy_role", "event_id", "case_id", "obligation_id", "attempt_id", "route_id") if k in priority} if priority else None,
        "questions_for_owner": [
            "Which actual obligation, original path, and replacement paths are in scope?",
            "Who decides whether to release again, and what evidence supports that decision?",
            "Which paths or records are missing, and when must the next decision be made?",
        ],
        "local_follow_up": {
            "actions": local_actions,
            "purchase_required": False,
            "scope": "Local code checks and supplied-record diagnostics remain useful independently of paid services.",
        },
        "workflow_follow_up": {
            "questions": [
                "Do all actual paths, including manual bank portals, use the decision under review?",
                "Who verifies final closure evidence and maps the same obligation across paths?",
                "Who owns the next change, and when must a release decision be made?",
            ],
            "scope": "These questions require evidence from the actual workflow. A synthetic match or incomplete history cannot answer them.",
            "assessment_optional": True,
        },
        "limits": [
            "Findings are bounded by the supplied records or synthetic contexts; counts are not monetary losses.",
            "Obligation mapping and final-evidence labels are operator assertions, not authenticated facts.",
            "No payment is executed, blocked, signed, or authorized. Production protection is not established.",
        ],
        "assessment": {
            "optional": True, "requires": "One actual workflow, an owner, original/backup paths, an agreed evidence scope, and an agreed fee.",
            "deliverables": "A workflow readout, one page of findings and next steps, and supporting records.",
            "progression": "Paid assessment, then shadow evaluation with no payment authority; selective enforcement requires technical validation and customer approval.",
            "url": ASSESSMENT_URL,
        },
    }
    if result.get("input_digest"):
        brief["input_digest"] = result["input_digest"]
    if result.get("comparison"):
        brief["comparison"] = dict(result["comparison"])
    if result.get("ci"):
        brief["ci"] = dict(result["ci"])
    return brief


def render_owner_html(result: dict) -> str:
    brief = build_owner_summary(result)

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def short(value: str, limit: int) -> str:
        return esc(value if len(value) <= limit else value[:limit - 1] + "…")

    source = "Synthetic data" if brief["source_type"] == "synthetic" else "Operator-supplied history"
    routes = brief["declared_routes"]
    route_text = "; ".join(f"{r['label']} ({r['coverage']})" for r in routes[:3])
    if len(routes) > 3:
        route_text += f"; {len(routes) - 3} more paths in the full report"
    paths = f'<p class="small"><strong>Declared paths:</strong> {short(route_text, 260)}</p>' if routes else ""
    priority = brief["priority_finding"]
    finding = short(priority["summary"], 230) if priority else "No priority finding in this result. Retain its scope and limits."
    refs = ", ".join(f"{key}: {value}" for key, value in (priority or {}).items() if key not in {"code", "summary"})
    reference = f'<p class="small">{short(refs, 200)}</p>' if refs else ""
    comparison = brief.get("comparison")
    changed = f'<p class="small"><strong>Policy change:</strong> {comparison["improved_count"]} improved; {comparison["regressed_count"]} regressed; {comparison["uncertain_count"]} uncertain; {comparison["after_mismatch_count"]} candidate mismatches. The absolute fixture contract still applies.</p>' if comparison else ""
    ci = brief.get("ci")
    ci_text = ""
    if ci:
        ci_text = f'<p class="small"><strong>CI mode:</strong> {esc(ci["mode"])}. Diagnostic exit {ci["diagnostic_exit_code"]}; process exit {ci["process_exit_code"]}.'
        if ci["mode"] == "report":
            ci_text += " Advisory completion does not erase findings or establish approval."
        ci_text += "</p>"
    local_actions = "".join(f"<li>{esc(q)}</li>" for q in brief["local_follow_up"]["actions"])
    workflow_questions = "".join(f"<li>{esc(q)}</li>" for q in brief["workflow_follow_up"]["questions"])
    limits = "".join(f"<li>{esc(q)}</li>" for q in brief["limits"])
    verdict_label, tone = VERDICT_LABELS[brief["verdict"]]
    digest = f'<span class="digest">Input digest: {esc(brief["input_digest"])}</span>' if brief.get("input_digest") else ""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><meta name="robots" content="noindex,nofollow">
<title>Workflow owner summary | Payment Control Lab</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f6f8f5;color:#142b35;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;overflow-wrap:anywhere}}main{{max-width:880px;margin:auto;padding:30px}}header{{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid #d4dedb;padding-bottom:14px}}.brand{{font-weight:800;letter-spacing:.04em}}.badge{{font-size:11px;background:#dae8f4;color:#24496a;padding:5px 9px;border-radius:5px}}h1{{font-size:28px;line-height:1.2;margin:24px 0 8px;letter-spacing:-.03em}}h2{{font-size:15px;margin:0 0 8px}}p{{margin:7px 0}}.muted{{color:#52646c}}.small{{font-size:12px}}section{{padding:16px 18px;border:1px solid #d4dedb;border-radius:9px;background:white;margin:14px 0}}.decision{{background:#e6f1eb;border-left:4px solid #18503b}}.decision.gap{{background:#f8e1d6;border-left-color:#872e1b}}.decision.unknown{{background:#f5e7cd;border-left-color:#69450d}}.decision.demo{{background:#dae8f4;border-left-color:#24496a}}.follow-up{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}.follow-up section{{margin:0 0 14px}}.metrics{{display:flex;flex-wrap:wrap;gap:12px 30px;font-size:12px;margin:14px 0}}.metrics strong{{font-size:22px;display:block}}ol,ul{{padding-left:20px;margin:6px 0}}li{{margin:4px 0}}a{{color:#285769;text-underline-offset:3px}}a:focus-visible{{outline:3px solid #176f7c;outline-offset:4px}}footer{{font-size:10px;color:#52646c;border-top:1px solid #d4dedb;padding-top:12px}}.digest{{display:block;font-family:ui-monospace,monospace;font-size:9px;margin-top:5px}}.assessment{{font-size:12px;background:#edf2f0}}@media(max-width:600px){{main{{padding:18px}}.follow-up{{grid-template-columns:1fr;gap:0}}header{{flex-wrap:wrap}}h1{{font-size:24px}}section{{padding:14px}}}}@page{{size:A4;margin:12mm}}@media print{{body{{background:white;font-size:10px;line-height:1.35}}main{{max-width:none;padding:0}}h1{{font-size:20px;margin-top:15px}}h2{{font-size:11px}}section{{padding:10px 12px;margin:9px 0;break-inside:avoid}}.small,.assessment{{font-size:9px}}.metrics{{margin:8px 0}}.metrics strong{{font-size:17px}}footer{{font-size:8px}}.digest{{font-size:7px}}.navigation{{display:none}}}}
</style></head><body><main>
<header><span class="brand">HALTSEAL · Payment Control Lab</span><span class="badge">{source}</span></header>
<h1>One workflow. A clear next decision.</h1><p class="muted">{short(brief['workflow_name'], 160)}</p>
<div class="metrics"><span><strong>{esc(verdict_label)}</strong>Diagnostic result</span><span><strong>{brief['finding_count']}</strong>{esc(brief['finding_label'])}</span><span><strong>{brief['evidence_gap_count']}</strong>Evidence gaps</span></div>
<section class="decision {tone}"><h2>Decision requested</h2><p>{esc(brief['decision_requested'])}</p><p class="small"><strong>Next step:</strong> {short(brief['next_step'], 250)}</p></section>
<section><h2>What was reviewed</h2><p>{esc(brief['scope_statement'])}</p>{paths}<p><strong>Priority:</strong> {finding}</p>{reference}{changed}{ci_text}</section>
<div class="follow-up"><section><h2>Continue with the free checks</h2><ul>{local_actions}</ul><p class="small">No purchase required.</p></section><section><h2>Validate one actual workflow</h2><ol>{workflow_questions}</ol><p class="small">{esc(brief['workflow_follow_up']['scope'])}</p></section></div>
<section><h2>Keep these limits attached</h2><ul class="small">{limits}</ul></section>
<section class="assessment"><h2>Optional paid workflow assessment</h2><p>Use this when one actual workflow needs a scoped review of its paths, evidence, and execution boundary. Agree the owner, evidence, fee, and deliverables first.</p><p>Deliverables: workflow readout, one page of findings and next steps, and supporting records. Shadow evaluation has no payment authority; enforcement requires technical validation and customer approval.</p><p><a href="{ASSESSMENT_URL}" rel="noreferrer">Discuss a workflow assessment</a>. This link does not attach or upload the report.</p></section>
<footer>Local diagnostics · v{esc(result['tool_version'])} · Scope and evidence limits apply.{digest}<p class="navigation"><a href="report.html">Full diagnostic report</a> · <a href="report.json">Structured result and complete owner summary</a></p></footer>
</main></body></html>'''
