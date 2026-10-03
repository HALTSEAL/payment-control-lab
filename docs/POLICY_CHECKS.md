# Local function checks

`check-policy` passes a separate copy of each synthetic context to `decide(context)`. Return exactly `ACCEPT`, `HOLD`, or `REFUSE`. The command imports and executes trusted local Python code without sandboxing or a callback timeout. Keep functions deterministic, fast, and free of side effects.

```sh
python lab.py check-policy my_workflow_policy:decide --out out/my-policy
```

The module is resolved through Python's import path, including the current working directory. It must not contain live execution calls or require production credentials.

## Context

| Field | Meaning in the synthetic fixture |
| --- | --- |
| `proposal` | Exact action fields from the workflow input contract |
| `obligation` | The mapped full obligation, amount, currency, payee, and display exponent |
| `prior_attempts` | Earlier mapped attempts, their recorded outcomes, `evidence_final`, and `evidence_origin` |
| `declared_coverage_complete` | Whether all declared fixture paths are represented; not a discovery of every real path |
| `approval_matches_proposal` | Whether the fixture's prior approval binds the exact proposal |
| `fresh_decision` | Whether fresh validation is established in the fixture |

All values are fixture assumptions, not authenticated facts. The check does not run your payment workflow, model a distributed transaction, verify credentials, or exercise production concurrency.

## Independent expectations

| Case | Allowed decision(s) |
| --- | --- |
| First exact payment | ACCEPT |
| Unresolved original, different route | HOLD or REFUSE |
| Unresolved original, same route new attempt | HOLD or REFUSE |
| Provisional failure | HOLD or REFUSE |
| Closure without final evidence | HOLD or REFUSE |
| Operator-note closure | HOLD or REFUSE |
| Provider final closure and fresh exact decision | ACCEPT |
| Original completed | REFUSE |
| Approval bound to another route | REFUSE |
| Changed amount, currency, or payee (three cases) | REFUSE |
| Fresh decision not established | REFUSE |
| Declared route unobserved | HOLD or REFUSE |
| Earlier attempt belongs to another independently mapped obligation | ACCEPT |
| Bank final closure and fresh exact decision | ACCEPT |

Some refusals may be conservative rather than unsafe. The policy report therefore labels deviations **fixture mismatches**, not recorded payment incidents. Valid-payment cases distinguish unnecessary refusal from useful control. The explicit fixture contract is reviewable in `payment_control_lab/data/policy-challenges.json`.

`examples/route_retry_policy.py` deliberately considers only a route and misses cross-route cases. `examples/fixture_policy.py` is a stateless teaching example for the declared contexts. Neither is a production adapter or HALTSEAL's commercial implementation.

Unsupported return values, ordinary callback exceptions, and callback `SystemExit` are inconclusive. A module that raises `SystemExit` during import is a configuration error. Exception types are retained; messages are omitted to avoid leaking data. Context copies prevent a function from accidentally mutating subsequent fixture inputs. This is not protection against malicious Python code.

## Compare a change

```sh
python lab.py compare-policy before_policy:decide after_policy:decide --out out/change
```

Both functions receive copies of the same fixture set, loaded once for the comparison. The report retains before/after decisions, statuses, and error types for each case. Improvements cannot cancel a regression or a remaining candidate mismatch. An unknown baseline makes the comparison incomplete; a matching candidate cannot establish an improvement against it. HOLD and REFUSE remain equivalent only where the fixture explicitly allows both.

Supply wrappers for the two code versions explicitly. The command does not fetch an older Git revision or isolate dependency and application state between functions. Use deterministic wrappers with mocked dependencies and isolated test state. See [CI adoption](ADOPT_IN_CI.md) for advisory and gate modes, the customer adapter, and workflow-owner review.
