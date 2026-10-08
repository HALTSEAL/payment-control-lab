# Payment Control Lab

**Catch risky payment changes before they ship. Give the workflow owner a clear next step.**

Offline diagnostics for a concrete question: **can the same payment obligation be released again while its original outcome remains unresolved?**

The lab reviews supplied records and checks trusted local decision functions against synthetic expectations. Compare a change, retain the checks in CI, and share a compact workflow-owner summary. Every completed diagnostic run writes `report.html`, `report.json`, and `owner-summary.html`. It does not execute, block, sign, or authorize payments.

**v0.2.0 · Python 3.11+ · No runtime dependencies · No account needed to run**

**Apache-2.0 · Publisher: Yong Bok Lee** See [LICENSE](LICENSE), [NOTICE](NOTICE) and [license status](LICENSE_STATUS.md). This diagnostic release does not establish production payment protection.

The intended public package contains the diagnostic runtime, synthetic examples, regression tests and usage guides. The public repository contains only the reviewed diagnostic Work, licensing and public development files. No production API or execution SDK is released by this repository.

## Start with your question

| Your next step | Start here | What you get |
| --- | --- | --- |
| Diagnose existing records or a decision function | [Payment Control Lab](https://github.com/HALTSEAL/payment-control-lab#five-minute-start) | Local diagnostic reports and an owner summary. No account needed. |
| Run exact-original recovery with a client | [Payments SDK](https://github.com/HALTSEAL/payments-sdk#choose-your-language) | A pinned Python or JavaScript synthetic exercise. No account needed. |
| Evaluate your actual application hooks | [Request the Workflow Evaluation Kit](https://haltseal.com/workspace/#kit) | Scoped private evaluator access after readiness review, then an integration map, execution record and owner decision. |

The Lab diagnoses supplied evidence. The SDK exercises explicit recovery calls.
The private kit observes connected local application hooks. A reference pass
verifies the kit; it does not establish customer coverage or production readiness.
Kit access does not require purchasing a pilot. Bring the resulting evidence to
an owner review, then [review the standard pilot](https://haltseal.com/pilot/start/)
or [ask about a different scope](https://haltseal.com/pricing/#request) if useful.

## Five-minute start

From a checkout, run one command:

```sh
python lab.py demo
```

Open `out/demo/report.html` in your browser. Open `owner-summary.html` for the compact operator brief; `report.json` retains the complete structured result. All fonts and styles are local; the reports use no JavaScript, remote assets, or telemetry.

If you need the checkout first:

```sh
git clone https://github.com/HALTSEAL/payment-control-lab.git
cd payment-control-lab
python lab.py demo
```

Use `python3` on macOS/Linux or `py` on Windows if `python` is not available. No `pip install` is needed for the checkout workflow. Use the reviewed checkout or the v0.2.0 Release assets. This project is not published to PyPI.

Start with two cases: a backup released while the first attempt is unresolved, and the same backup held. Then inspect final evidence, a changed route, a reused decision, and an unobserved bank portal.

| Command | What you get |
| --- | --- |
| `python lab.py demo` | 16 synthetic traces, with their expected diagnoses |
| `python lab.py demo --case lost-response` | One focused explanation of an unresolved original and released backup |
| `python lab.py list` | Names of all built-in trace cases |
| `python lab.py review examples/workflow.json` | Review of the included synthetic workflow file |
| `python lab.py template --out workflow.json` | An empty template for your redacted history |
| `python lab.py check-policy examples.route_retry_policy:decide` | 16 synthetic challenges against deliberately limited per-route logic |
| `python lab.py check-policy examples.fixture_policy:decide` | The same challenges against a stateless fixture example |
| `python lab.py compare-policy examples.route_retry_policy:decide examples.fixture_policy:decide` | Before/after decisions, improvements, regressions, and unknowns for the same 16 contexts |

The intentionally limited policy command exits **2** because its returned decisions differ from the fixtures. The fixture example is teaching code, not HALTSEAL's production implementation or a deployable payment control.

## Review your own workflow

```sh
python lab.py template --out workflow.json
# Replace aliases and add your redacted event records.
python lab.py review workflow.json --out out/my-workflow
```

The input links decisions, releases, and outcomes to an operator-mapped obligation. Use one alias for the same obligation across providers and portals. The lab cannot discover that two different aliases secretly refer to the same obligation.

Read the [input format](docs/INPUT_FORMAT.md) before mapping real data. The [JSON Schema](schemas/workflow.schema.json) documents the structural contract. Chronology, unique aliases, and cross-references also receive semantic validation.

Never include bank account numbers, credentials, personal names, email addresses, or full provider responses. The lab does not automatically redact free-text labels or establish that your input is de-identified. Generated JSON reports retain the supplied event records; HTML exposes permitted labels, findings, and record references.

## Check your own decision function

Create a trusted local module with `decide(context)` and return `ACCEPT`, `HOLD`, or `REFUSE`:

```sh
python lab.py check-policy my_workflow_policy:decide --out out/my-policy
```

The [policy contract](docs/POLICY_CHECKS.md) defines each context field and expected outcome. Valid-payment cases prevent an always-refuse implementation from passing. Expectations are authored separately from the passive trace analyzer.

This command imports and executes code you explicitly supply. Use a trusted, fast, side-effect-free local function. Callables are not sandboxed; their imports and actions are outside the bundled diagnostics' offline guarantee. Do not point this command at payment execution functions.

## Check the next change in CI

```sh
python lab.py compare-policy my_policy_before:decide my_policy_after:decide --out out/payment-change
```

Supply two wrappers that call the corresponding application code versions. The candidate must meet every bundled expectation: improvements cannot cancel one regression, and an unchanged failing baseline does not pass. Unknown baseline behavior makes the comparison incomplete. The lab does not discover or check out the old version for you.

Start with `--ci-mode report` to retain diagnostic findings without blocking software changes. After agreeing the contract and review owner, use `--ci-mode gate` (the default) to preserve nonzero diagnostic exits. Report mode never hides invalid input, import failures, or output errors. **An advisory exit 0 is not an approval.**

Use the [adapter and CI guide](docs/ADOPT_IN_CI.md) and the [customer workflow template](examples/ci/payment-control.yml). The adapter is deliberately unconfigured; connecting your actual decision code is required. The template requires an authorized checkout and is not already installed in a customer repository.

## Read the result correctly

| Trace verdict | Meaning |
| --- | --- |
| `CONTROL_GAP_OBSERVED` | Supplied records contain a supported finding, such as an overlapping release or changed approved action. This is not proof of a duplicated monetary effect. |
| `INCONCLUSIVE` | Missing or conflicting evidence prevents a supported conclusion. |
| `NO_FINDING_IN_TRACE` | No finding within the supplied records and declared scope. This does not establish production protection. |

Policy checks use `EXPECTATIONS_MET`, `EXPECTATIONS_NOT_MET`, or `INCONCLUSIVE`, because a synthetic function comparison is different from an observed execution trace.

| Exit code | Meaning |
| --- | --- |
| `0` | In gate mode: no finding in scope or fixture expectations matched. Demo: expected diagnoses reproduced. Report mode: completed diagnostics, including findings and unknowns. |
| `1` | Invalid input, configuration, or report output |
| `2` | Recorded finding or policy fixture mismatch |
| `3` | Inconclusive evidence or callable result |

**Demo exit 0 only means the expected synthetic diagnoses were reproduced.** Do not use the demo command as an approval gate. `report.json` records both diagnostic and process exits when `--ci-mode` applies. See [interpreting results](docs/INTERPRETING_RESULTS.md) for CI use and limitations.

## Bring one workflow to a paid assessment

The free diagnostics work independently of HALTSEAL's paid services. Fix local code, improve record mapping, and keep the checks in CI without purchasing a service. Each result separates those actions from questions about actual path coverage, final evidence, and the decision owner.

If one actual workflow needs help answering those questions, [discuss a scoped paid workflow assessment](https://haltseal.com/evaluate/?source=payment-control-lab#contact).

Bring the original path, the backup path, and the role that decides whether to release again. The next deliverable is one workflow readout, one page of findings and next steps, and supporting records. Further work can proceed to shadow evaluation with no payment authority; selective enforcement requires technical validation and customer approval. See [assessment scope](docs/WORKFLOW_ASSESSMENT.md).

CLI reports stay local. The assessment link does not upload them. The optional customer CI template uploads the three reports to GitHub with explicit retention; agree access and review permitted labels before adopting it.

## Development and packaging

```sh
python -m unittest discover -v
```

The repository includes strict-input, outcome-finality, overlapping-release, action-binding, missing-coverage, report-escaping, callback-error, before/after regression, advisory/gate, owner-summary, and CLI tests. The GitHub workflow configures these checks on Python 3.11–3.14 and Windows, builds a wheel, and checks its bundled resources from a separate directory. See the [local verification record](docs/VERIFICATION.md) for completed checks and their limits.

Optional install from a checkout:

```sh
python -m pip install .
payment-control-lab demo
```

Build tooling may need package downloads during installation. The direct checkout command and bundled runtime diagnostics do not. This project is not published to PyPI.

## Scope

v0.2 retains the version 0.1 input contract and models one complete payment per obligation. It does not model partial payments, netting, refunds, FX conversion, live provider adapters, authority revocation, distributed concurrency guarantees, or all paths in an organization. A provider/bank final-evidence label is accepted only as an operator-supplied assertion, never cryptographically authenticated.

The synthetic fixtures establish expected lab behavior. They are not a third-party audit, an industry certification, or a demonstration of production readiness. See [release scope](docs/RELEASE_SCOPE.md), [security](SECURITY.md), and [contributing](CONTRIBUTING.md).

Built by **Scott Lee** for **HALTSEAL**.
