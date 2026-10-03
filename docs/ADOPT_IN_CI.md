# Use the lab on the next payment-code change

The recurring job is to check your own decision logic when retries, fallback routes, approval binding, or evidence handling change. The lab remains useful if you fix the code yourself and never buy HALTSEAL services.

## 1. Reproduce a change, without payment access

From this checkout:

```sh
python lab.py compare-policy examples.route_retry_policy:decide examples.fixture_policy:decide --out out/change
```

Open `out/change/report.html` for the before/after cases and `out/change/owner-summary.html` for the compact owner brief. JSON contains both the comparison and the complete structured owner summary. These functions are teaching examples; the command has not inspected your application.

The candidate must meet the absolute contract. A smaller total mismatch count cannot cancel one newly failing case. An unchanged failing baseline also fails. A baseline exception makes the comparison incomplete even if the candidate matches every expectation. HOLD-to-REFUSE changes remain equivalent only in cases that explicitly allow both decisions.

## 2. Bind your existing decision logic

Copy `examples/customer_adapter.py` into **your** repository as `payment_policy_adapter.py`. Replace its body with a call to the decision function already used by your application. Map the returned values explicitly to `ACCEPT`, `HOLD`, or `REFUSE`; do not replace the application logic with a function that just returns the expected answers.

The template intentionally raises `NotImplementedError`. An unbound adapter produces an inconclusive result, never a fixture pass. The [policy contract](POLICY_CHECKS.md) defines every supplied field and allowed result. Inject mocked dependencies and reset any test state for each context. Import and callback execution are trusted local code, not a sandbox. There is no per-callback timeout; keep your CI job bounded and your wrapper fast.

Run from your application root, using an authorized checkout of the lab:

```sh
python /path/to/payment-control-lab/lab.py check-policy payment_policy_adapter:decide --ci-mode report --out out/payment-control
```

An installed, licensed distribution can use `payment-control-lab` in place of that script path. There is currently no PyPI release. The first integration target is a 30–60 minute setup; it is a target to validate with external teams, not a measured performance claim.

Passing checks means this wrapper matched sixteen synthetic contexts. It does not prove that production calls this function, all paths are covered, concurrent releases are serialized, or evidence is authenticated. Review those questions with the workflow owner.

## 3. Begin advisory, then agree a gate

| Mode | Finding or fixture mismatch | Inconclusive result | Invalid input, import, or report output |
| --- | --- | --- | --- |
| `--ci-mode report` | Process exit 0; diagnostic exit 2 remains in JSON and HTML | Process exit 0; diagnostic exit 3 remains | Exit 1 |
| `--ci-mode gate` (default) | Exit 2 | Exit 3 | Exit 1 |

Advisory completion is not an approval. Verdicts, findings, evidence gaps, and counts stay intact. Agree which contract your team expects, what the wrapper exercises, and who reviews findings before enabling a PR gate. This gate affects software changes, not live payment execution. Never use `demo` as the check: demo success only reproduces authored examples.

The [customer workflow template](../examples/ci/payment-control.yml) checks your adapter and uploads the three-file report bundle even after a diagnostic failure. Replace the placeholder with a reviewed full commit SHA. It is a customer template, not a workflow already installed in your repository. While the lab is private, another repository needs separately authorized checkout access; a normal consumer token does not automatically grant access. A public checkout requires the release/license decision first.

The template also displays the actual diagnostic verdict, evidence gaps, mode, and diagnostic/process exit codes in the GitHub job summary. It does not include free-text workflow labels or event records there. The report directory is cleared before the check; a failed setup skips report collection, and an incomplete diagnostic run is never represented by an older report.

Use ordinary `pull_request`, read-only permissions, and no production secrets. Do not execute PR-controlled adapters through `pull_request_target` or a privileged publishing job. GitHub artifact upload **does** transfer the generated files to GitHub; agree access and retention with your organization. Use synthetic contexts and redacted labels, and never upload real payment records by default.

## 4. Compare the actual change

Keep two importable wrappers with isolated test state, for example `payment_policy_before:decide` and `payment_policy_after:decide`, that invoke the corresponding code versions. Supply both explicitly:

```sh
python /path/to/payment-control-lab/lab.py compare-policy payment_policy_before:decide payment_policy_after:decide --ci-mode gate --out out/payment-change
```

The lab does not check out an old Git revision or discover the before version automatically. Wrappers run sequentially in one Python process. For changed dependencies or stateful implementations, arrange separate test isolation before comparing; these contexts do not model distributed execution.

## 5. Bring the result to the workflow owner

Share `owner-summary.html` with its companion `report.html` and `report.json` after reviewing labels. The brief keeps source type, scope, priority reference, unknowns, comparison, and diagnostic/process exit codes together. Long fields are shortened in HTML; JSON retains the complete brief. Local commands do not upload these files.

Agree the actual obligation, original and backup paths (including manual portals), decision owner, evidence gaps, and deadline. Use `review` for normalized historical records as a separate evidence source. A policy comparison cannot establish an actual customer incident, and a record review cannot prove unobserved behavior.

If that workflow needs a scoped review of mapping, coverage, final evidence, or the execution boundary, the [paid assessment](WORKFLOW_ASSESSMENT.md) is an optional next step. Keep the checks in CI after the review so the team continues to get value on future changes.
