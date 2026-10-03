# Copyright 2026 Yong Bok Lee
# SPDX-License-Identifier: Apache-2.0
"""Self-contained, escaped, script-free HTML and structured JSON reports."""

from __future__ import annotations

import html
import json
import os
import shutil
import tempfile
from pathlib import Path

from .input import InputError
from .owner_summary import ASSESSMENT_URL, build_owner_summary, render_owner_html

LABELS = {
    "CONTROL_GAP_OBSERVED": ("Control gap observed", "gap", "The supplied records contain a decision or release that needs review."),
    "INCONCLUSIVE": ("More evidence needed", "unknown", "The supplied records are not sufficient for a conclusion about this workflow."),
    "NO_FINDING_IN_TRACE": ("No finding in this trace", "clear", "No supported finding was identified within the supplied records and declared scope."),
    "EXPECTATIONS_NOT_MET": ("Fixture expectations not met", "gap", "The local function differs from one or more explicitly documented synthetic expectations."),
    "EXPECTATIONS_MET": ("Fixture expectations met", "clear", "The local function matched the bundled expectations. This is not production verification."),
    "SYNTHETIC_DEMO": ("Synthetic demonstration", "demo", "See what changes when a backup is released, held, or checked against final evidence."),
}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def money(obligation: dict) -> str:
    exponent = obligation["minor_unit_exponent"]
    whole, fraction = divmod(obligation["amount_minor"], 10**exponent)
    amount = f"{whole:,}" + (f".{fraction:0{exponent}d}" if exponent else "")
    return f"{obligation['currency']} {amount}"


def _findings(result: dict) -> str:
    rows = sorted(result["findings"], key=lambda f: f["category"] == "evidence_gap")
    if not rows:
        if result["kind"] in {"policy_challenge", "policy_comparison"}:
            return '<div class="notice clear"><strong>All fixture expectations matched.</strong><p>This establishes agreement with the supplied synthetic contexts only.</p></div>'
        return '<div class="notice clear"><strong>No finding in the supplied scope.</strong><p>Keep the scope and evidence limits attached when sharing this result.</p></div>'
    output = []
    for finding in rows[:200]:
        tone = "unknown" if finding["category"] == "evidence_gap" else "gap"
        label = "Evidence gap" if tone == "unknown" else "Fixture mismatch" if finding["category"] == "fixture_mismatch" else "Recorded control gap"
        refs = {k: v for k, v in finding.items() if k not in {"summary", "next_step", "category"}}
        output.append(f'<article class="finding {tone}"><span class="eyebrow">{label}</span><h3>{esc(finding["summary"])}</h3><p><strong>Next step</strong> {esc(finding["next_step"])}</p><details><summary>Inspect record references</summary><pre>{esc(json.dumps(refs, indent=2))}</pre></details></article>')
    if len(rows) > 200:
        output.append(f'<p class="muted">Showing 200 of {len(rows)} findings. The JSON report contains every finding.</p>')
    return "".join(output)


def _trace(result: dict, compact: bool = False) -> str:
    scope = result["scope"]
    routes = "".join(f'<li><span>{esc(r["label"])}</span><span class="pill {"clear" if r["coverage"] == "captured" else "unknown"}">{"Records supplied" if r["coverage"] == "captured" else "Unobserved"}</span></li>' for r in scope["routes"])
    obligations = "".join(f'<li><strong>{esc(money(o))}</strong><span>{esc(o["obligation_id"])} · {esc(o["payee_ref"])}</span></li>' for o in scope["obligations"][:20])
    if len(scope["obligations"]) > 20:
        obligations += f'<li class="muted">{len(scope["obligations"]) - 20} additional obligations are listed in JSON.</li>'
    timeline = "".join(f'<li><span class="event-kind">{esc(e["type"])}</span><div><strong>{esc(e["detail"])}</strong><span class="mono muted">{esc(e["at"])} · {esc(e["event_id"])}</span></div></li>' for e in result["timeline"][:200])
    if not timeline:
        timeline = '<li class="muted">No event records supplied.</li>'
    if len(result["timeline"]) > 200:
        timeline += '<li class="muted">Timeline preview limited to 200 events. All reviewed events are listed in JSON.</li>'
    if compact:
        return f'<h4>Recorded flow</h4><ol class="timeline">{timeline}</ol><h4>Findings and next steps</h4>{_findings(result)}'
    return f'<div class="two-col"><section class="panel"><h2>Recorded flow</h2><ol class="timeline">{timeline}</ol></section><aside class="panel"><h2>Declared scope</h2><h3>Execution paths</h3><ul class="scope-list">{routes}</ul><h3>Mapped obligations</h3><ul class="obligations">{obligations}</ul><p class="muted small">“Records supplied” is an operator declaration. It does not establish that all events or all possible paths were captured.</p></aside></div><section class="panel"><h2>Findings and next steps</h2>{_findings(result)}</section>'


def _policy_table(result: dict) -> str:
    rows = "".join(f'<tr><td><strong>{esc(r["title"])}</strong><span class="mono muted small">{esc(r["case_id"])}</span></td><td>{esc(" or ".join(r["allowed_decisions"]))}</td><td>{esc(r["observed_decision"] or "No valid decision")}</td><td><span class="pill {"clear" if r["status"] == "MATCH" else "unknown" if r["status"] == "INCONCLUSIVE" else "gap"}">{esc(r["status"])}</span></td></tr>' for r in result["policy_cases"])
    return f'<section class="panel"><h2>Independent fixture expectations</h2><p class="muted">These outcomes test the declared synthetic contract, including valid payments. They are not a simulation of actual execution or a certification.</p><p class="small muted">On narrow screens, scroll the comparison horizontally.</p><div class="table-wrap" tabindex="0" role="region" aria-label="Policy comparison table"><table><thead><tr><th>Case</th><th>Expected</th><th>Returned</th><th>Comparison</th></tr></thead><tbody>{rows}</tbody></table></div></section><section class="panel"><h2>What to review</h2>{_findings(result)}</section>'


def _comparison_table(result: dict) -> str:
    comparison = result["comparison"]
    rows = []
    for row in result["comparison_cases"]:
        tone = "unknown" if "INCONCLUSIVE" in {row["before_status"], row["after_status"]} else "gap" if row["after_status"] == "MISMATCH" else "clear"
        rows.append(f'<tr><td><strong>{esc(row["title"])}</strong><span class="mono muted small">{esc(row["case_id"])}</span></td><td>{esc(" or ".join(row["allowed_decisions"]))}</td><td>{esc(row["before_decision"] or "No valid decision")}<span class="small muted"> ({esc(row["before_status"])})</span></td><td>{esc(row["after_decision"] or "No valid decision")}<span class="small muted"> ({esc(row["after_status"])})</span></td><td><span class="pill {tone}">{esc(row["transition"].replace("_", " ").lower())}</span></td></tr>')
    return f'<section class="panel"><h2>Before and after, case by case</h2><p>{comparison["improved_count"]} improved · {comparison["regressed_count"]} regressed · {comparison["uncertain_count"]} uncertain · {comparison["after_mismatch_count"]} candidate mismatches</p><p class="muted">Every candidate must meet the absolute fixture contract. Improvements in other cases cannot cancel a regression or a remaining mismatch. An unknown baseline cannot establish an improvement.</p><p class="mono small">Before: {esc(comparison["before_policy"])}<br>After: {esc(comparison["after_policy"])}</p><p class="small muted">On narrow screens, scroll the comparison horizontally.</p><div class="table-wrap" tabindex="0" role="region" aria-label="Before and after policy comparison"><table><thead><tr><th>Case</th><th>Expected</th><th>Before</th><th>After</th><th>Change</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section><section class="panel"><h2>What to review</h2>{_findings(result)}</section>'


def render_html(result: dict) -> str:
    summary = result["summary"]
    title, tone, explanation = LABELS[summary["verdict"]]
    kind = result["kind"]
    source = "Synthetic data" if result["source_type"] == "synthetic" else "Operator-supplied history"
    if kind == "demo_suite":
        headline = "A new route is not<br>a new right to pay."
        cards = []
        for case in result["cases"]:
            label, case_tone, _ = LABELS[case["summary"]["verdict"]]
            reproduced = case["summary"]["verdict"] == case["expected_verdict"]
            cards.append(f'<article class="case-card"><div class="case-head"><span class="pill {case_tone}">{esc(label)}</span><span class="mono small">{esc(case["case_id"])}</span></div><h3>{esc(case["workflow_name"])}</h3><p>{esc(case["question"])}</p><details><summary>Inspect this trace</summary>{_trace(case, True)}<p class="muted small">{"Expected diagnosis reproduced." if reproduced else "Unexpected diagnosis; review the fixture."}</p></details></article>')
        main = '<section class="panel"><h2>One obligation. Different recorded outcomes.</h2><p class="muted">Start with “Lost response, released backup” and “Lost response, held backup.” Then inspect evidence, action changes, and missing paths.</p><div class="case-grid">' + "".join(cards) + '</div></section>'
        metric3, metric3_label = summary["case_count"], "Synthetic traces"
        metric4, metric4_label = f'{summary["diagnoses_reproduced"]}/{summary["case_count"]}', "Expected diagnoses reproduced"
        next_step = "Run your own redacted records or local decision function. Keep incomplete paths visible, then choose one workflow to review with its owner."
    elif kind in {"policy_challenge", "policy_comparison"}:
        headline = esc(title)
        main = _comparison_table(result) if kind == "policy_comparison" else _policy_table(result)
        metric3, metric3_label = len(result["policy_cases"]), "Synthetic challenges"
        metric4, metric4_label = sum(r["status"] == "MATCH" for r in result["policy_cases"]), "Expectations matched"
        next_step = result["findings"][0]["next_step"] if result["findings"] else "Retain these regression checks, then validate event capture, evidence authority, and actual execution behavior separately."
    else:
        headline = esc(title)
        main = _trace(result)
        metric3, metric3_label = len(result["scope"]["obligations"]), "Mapped obligations"
        metric4, metric4_label = result["scope"]["event_count"], "Supplied events"
        priority = next((f for f in result["findings"] if f["category"] != "evidence_gap"), None)
        priority = priority or next(iter(result["findings"]), None)
        next_step = priority["next_step"] if priority else "Keep this result limited to the reviewed trace. Confirm omitted paths and evidence authority before changing production controls."
    limitations = "".join(f'<li>{esc(line)}</li>' for line in result["limitations"])
    fingerprint = f'<p class="mono muted small">Input digest: {esc(result["input_digest"])}</p>' if result.get("input_digest") else ""
    ci_notice = ""
    if result.get("ci"):
        ci = result["ci"]
        advisory = " Findings and evidence gaps remain visible. Advisory completion is not an approval." if ci["mode"] == "report" else " Diagnostic findings and inconclusive results retain their nonzero exit codes."
        ci_notice = f'<p class="small muted"><strong>CI mode: {esc(ci["mode"])}</strong> · Diagnostic exit {ci["diagnostic_exit_code"]}; process exit {ci["process_exit_code"]}.{advisory}</p>'
    brief = build_owner_summary(result)
    local_actions = "".join(f"<li>{esc(line)}</li>" for line in brief["local_follow_up"]["actions"])
    workflow_questions = "".join(f"<li>{esc(line)}</li>" for line in brief["workflow_follow_up"]["questions"])
    follow_up = f'<div class="two-col"><section class="panel"><h2>Continue with the free checks</h2><ul class="limits">{local_actions}</ul><p class="small">No purchase required. Keep using the checks independently of paid services.</p></section><section class="panel"><h2>Validate one actual workflow</h2><ul class="limits">{workflow_questions}</ul><p class="small muted">{esc(brief["workflow_follow_up"]["scope"])}</p></section></div>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><meta name="robots" content="noindex,nofollow">
<title>{esc(result["workflow_name"])} | Payment Control Lab</title>
<style>
:root{{--ink:#142b35;--muted:#52646c;--paper:#f6f8f5;--line:#d4dedb;--mint:#d8eee5;--orange:#f7dfcf;--blue:#dae8f4;--gap:#872e1b;--unknown:#69450d;--clear:#18503b}}
*{{box-sizing:border-box}}body{{margin:0;overflow-wrap:anywhere;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.6}}a{{color:inherit;text-underline-offset:4px}}a:focus-visible,summary:focus-visible{{outline:3px solid #176f7c;outline-offset:5px}}.wrap{{max-width:1180px;margin:auto;padding:0 32px}}header{{border-bottom:1px solid var(--line)}}.top{{min-height:86px;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;padding-top:16px;padding-bottom:16px}}.brand{{font-size:20px;font-weight:850;letter-spacing:.04em}}.brand span{{display:block;font-size:12px;font-weight:600;letter-spacing:.03em;color:var(--muted)}}.pill{{display:inline-flex;padding:5px 10px;border-radius:6px;font-size:12px;font-weight:700;line-height:1.4}}.pill.gap{{background:#f8e1d6;color:var(--gap)}}.pill.unknown{{background:#f5e7cd;color:var(--unknown)}}.pill.clear{{background:var(--mint);color:var(--clear)}}.pill.demo{{background:var(--blue);color:#24496a}}.hero{{padding:54px 0 30px;display:grid;grid-template-columns:1.35fr .8fr;gap:38px;align-items:center}}.eyebrow{{font-size:11px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}}h1{{font-size:clamp(32px,4.4vw,54px);line-height:1.12;letter-spacing:-.04em;margin:16px 0 18px;font-weight:780}}h2{{font-size:23px;line-height:1.25;letter-spacing:-.02em;margin:0 0 16px}}h3{{font-size:16px;line-height:1.45;margin:10px 0}}h4{{margin:22px 0 10px;font-size:14px}}p{{margin:10px 0}}.lede{{font-size:17px;max-width:680px;color:var(--muted)}}.decision{{background:white;border:1px solid var(--line);border-top:4px solid #86b7a4;border-radius:12px;padding:25px;box-shadow:0 8px 30px #142b3505}}.decision.gap{{border-top-color:#d58559}}.decision.unknown{{border-top-color:#be9959}}.decision.demo{{border-top-color:#709cbf}}.decision strong{{display:block;font-size:23px;line-height:1.3;margin:13px 0}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:0 0 28px}}.metric{{border:1px solid var(--line);border-radius:10px;background:white;padding:18px 20px}}.metric strong{{font-size:27px;display:block;line-height:1.3}}.metric span{{font-size:12px;color:var(--muted);display:block;margin-top:6px}}.panel{{background:white;border:1px solid var(--line);border-radius:12px;padding:28px;margin-bottom:24px;min-width:0}}.two-col{{display:grid;grid-template-columns:1.45fr 1fr;gap:24px}}.muted{{color:var(--muted)}}.small{{font-size:12px}}.mono,pre{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;overflow-wrap:anywhere}}.timeline{{list-style:none;margin:0;padding:0}}.timeline li{{display:grid;grid-template-columns:78px 1fr;gap:14px;padding:15px 0;border-bottom:1px solid #e6ece9;font-size:13px}}.timeline li:last-child{{border:0}}.timeline strong{{display:block;font-weight:650}}.timeline .mono{{display:block;font-size:10px;margin-top:5px}}.event-kind{{align-self:start;background:#edf2f0;color:#34505a;border-radius:5px;text-align:center;padding:4px;font-size:11px;font-weight:700}}.scope-list,.obligations{{list-style:none;padding:0;margin:12px 0 24px}}.scope-list li{{display:flex;justify-content:space-between;align-items:center;gap:10px;border-bottom:1px solid #e6ece9;padding:11px 0;font-size:13px}}.obligations li{{display:flex;flex-direction:column;font-size:12px;margin:13px 0;overflow-wrap:anywhere}}.obligations strong{{font-size:19px}}.finding{{border:1px solid #e6d0c4;border-left:3px solid #d58559;border-radius:8px;padding:19px 22px;margin:14px 0}}.finding.unknown{{border-color:#e4d9c2;border-left-color:#be9959}}.finding p{{font-size:13px;color:var(--muted)}}.finding p strong{{color:var(--ink);display:block;margin-bottom:3px}}details{{margin-top:12px}}summary{{cursor:pointer;font-size:12px;font-weight:650;color:#285769;padding:3px 0;min-height:28px}}pre{{white-space:pre-wrap;font-size:11px;border:1px solid var(--line);background:#f5f8f6;padding:14px;border-radius:6px}}.notice{{padding:18px;border-radius:8px;background:#edf5f0;font-size:14px}}.notice p{{font-size:13px;color:var(--muted)}}.case-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:24px}}.case-card{{border:1px solid var(--line);padding:22px;border-radius:10px;background:#fbfcfb;min-width:0}}.case-card p{{font-size:13px;color:var(--muted)}}.case-head{{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}}.case-head .mono{{font-size:10px;color:var(--muted)}}.limits{{padding-left:20px;font-size:13px;color:var(--muted)}}.limits li{{margin:10px 0}}.next{{background:#e6f1eb}}.next p{{font-size:16px}}.assessment{{display:grid;grid-template-columns:1.5fr 1fr;gap:30px;align-items:center;background:#142b35;color:white;border:0}}.assessment p{{color:#ccd9d8;font-size:14px}}.assessment h2{{font-size:26px}}.button{{display:inline-flex;align-items:center;justify-content:center;text-decoration:none;background:#d8eee5;color:#142b35;border-radius:7px;padding:13px 19px;font-size:13px;font-weight:750;text-align:center}}.assessment .small{{font-size:11px}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;text-align:left;font-size:13px;min-width:580px}}th{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}th,td{{padding:14px 12px;border-bottom:1px solid #e6ece9;vertical-align:top}}td .mono{{display:block;margin-top:4px}}footer{{padding:12px 0 42px;font-size:12px;color:var(--muted);display:flex;gap:20px;justify-content:space-between;flex-wrap:wrap}}.sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
@media(max-width:760px){{.wrap{{padding:0 18px}}.hero{{grid-template-columns:1fr;gap:20px;padding-top:30px}}.metrics{{grid-template-columns:1fr 1fr}}.two-col,.case-grid,.assessment{{grid-template-columns:1fr}}.panel{{padding:21px}}.decision{{padding:22px}}h1{{font-size:36px}}.timeline li{{grid-template-columns:65px 1fr;gap:10px}}.case-card{{padding:18px}}.finding{{padding:17px}}.scope-list li{{align-items:start}}.assessment .button{{width:100%}}}}
@media print{{body{{background:white;font-size:11px}}.wrap{{max-width:none;padding:0}}header{{border:0}}.hero{{padding:15px 0;gap:20px}}h1{{font-size:26px}}.metrics{{margin-bottom:15px}}.metric{{padding:10px}}.panel{{padding:16px;box-shadow:none;break-inside:avoid}}.assessment{{display:none}}.case-grid{{grid-template-columns:1fr 1fr}}.finding{{break-inside:avoid}}footer{{padding:0}}}}
</style></head><body>
<header><div class="wrap top"><div class="brand">HALTSEAL<span>Payment Control Lab · v{esc(result['tool_version'])}</span></div><span class="pill {"demo" if result['source_type'] == 'synthetic' else 'unknown'}">{source}</span></div></header>
<main class="wrap"><section class="hero"><div><span class="eyebrow">Decision before action. Proof before consequence.</span><h1>{headline}</h1><p class="lede">{esc(result['workflow_name'])}</p></div><aside class="decision {tone}"><span class="eyebrow">What this report establishes</span><strong>{esc(title)}</strong><p class="muted">{esc(explanation)}</p></aside></section>
<p class="small"><a href="owner-summary.html">Open the workflow owner summary</a></p>{ci_notice}
<section class="metrics" aria-label="Review summary"><div class="metric"><strong>{summary['finding_count']}</strong><span>{"Fixture mismatches" if kind in {'policy_challenge', 'policy_comparison'} else 'Recorded findings'}</span></div><div class="metric"><strong>{summary['evidence_gap_count']}</strong><span>Evidence gaps</span></div><div class="metric"><strong>{metric3}</strong><span>{metric3_label}</span></div><div class="metric"><strong>{metric4}</strong><span>{metric4_label}</span></div></section>
<section class="panel next"><span class="eyebrow">The next decision</span><p>{esc(next_step)}</p></section>
{main}
{follow_up}
<section class="panel"><h2>Keep these limits with the result</h2><ul class="limits">{limitations}</ul>{fingerprint}<a class="small" href="report.json">Open the structured JSON report</a></section>
<section class="panel assessment"><div><span class="eyebrow" style="color:#c0d7d0">Optional paid workflow assessment</span><h2>One workflow.<br>A clear next decision.</h2><p>Bring the original path, the backup path, and the person who decides whether to release again. HALTSEAL can scope a paid assessment, then a shadow evaluation with no payment authority.</p></div><div><a class="button" href="{ASSESSMENT_URL}" rel="noreferrer">Discuss a workflow assessment</a><p class="small">The free lab works independently. Your report stays local; this link does not upload it. Share only after redaction.</p></div></section>
</main><footer class="wrap"><span>Offline diagnostics. No payment authority.</span><span>Built by Scott Lee · HALTSEAL</span></footer></body></html>'''


def write_report(result: dict, out: Path, input_path: Path | None = None) -> tuple[Path, Path]:
    targets = [out / "report.html", out / "report.json", out / "owner-summary.html"]
    result = dict(result, owner_summary=build_owner_summary(result))
    try:
        if input_path and any(p.resolve() == input_path.resolve() for p in targets):
            raise InputError("The report output would overwrite the input file; choose another output directory.")
        if any(p.is_symlink() for p in targets):
            raise InputError("Report output files must not be symlinks.")
        if any(p.exists() and not p.is_file() for p in targets):
            raise InputError("Report output paths must be regular files; choose another output directory.")
        out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".lab-report-", dir=out) as staging:
            staged = Path(staging)
            (staged / "report.html").write_text(render_html(result), encoding="utf-8")
            (staged / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (staged / "owner-summary.html").write_text(render_owner_html(result), encoding="utf-8")
            backups, installed = {}, []
            for target in targets:
                if target.exists():
                    backup = staged / ("previous-" + target.name)
                    shutil.copyfile(target, backup)
                    backups[target] = backup
            try:
                for target in targets:
                    os.replace(staged / target.name, target)
                    installed.append(target)
            except BaseException:
                for target in reversed(installed):
                    if target in backups:
                        os.replace(backups[target], target)
                    else:
                        target.unlink()
                raise
    except (OSError, UnicodeError):
        raise InputError("Cannot write the report; check the output directory and permissions.") from None
    return targets[0], targets[1]
