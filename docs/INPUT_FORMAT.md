# Workflow input, version 0.1

The input is a normalized, redacted record supplied by an operator. It is not a live payment request. [examples/workflow.json](../examples/workflow.json) is a complete synthetic example. [examples/workflow-template.json](../examples/workflow-template.json) is an empty history template; reviewing it is inconclusive until records are supplied.

## Top-level fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Exactly `0.1` |
| `source_type` | `synthetic` for invented examples; `redacted_history` for normalized historical records |
| `workflow_name` | A redacted label, maximum 120 characters |
| `routes` | Declared possible execution paths and their supplied coverage |
| `obligations` | Operator-mapped full payment obligations |
| `events` | Chronologically ordered decision, release, and outcome records |

An alias contains ASCII letters, digits, `.`, `_`, `:`, or `-`, starts with a letter or digit, and has at most 80 characters. Avoid recognizable customer identifiers. Unexpected fields are rejected; do not embed raw logs or evidence bodies.

Labels support multilingual Unicode text. Unpaired surrogates, control characters, and bidirectional formatting overrides are rejected so a label cannot break output encoding or disguise the displayed result.

## Routes and obligations

```json
{
  "route_id": "bank-portal",
  "label": "Manual bank portal",
  "coverage": "unobserved"
}
```

`captured` means the operator supplies records for that route in the review window. It is not verified coverage. `unobserved` creates an evidence gap even if the captured processor paths have no finding. Undeclared paths cannot be discovered automatically.

```json
{
  "obligation_id": "invoice-001",
  "amount_minor": 125000,
  "currency": "USD",
  "minor_unit_exponent": 2,
  "payee_ref": "payee-001"
}
```

Amounts are positive integers, never floats or booleans, with a maximum of 9,007,199,254,740,991. The exponent is explicitly supplied for display: 2 renders USD 1,250.00; 0 can render JPY; 3 can render KWD. Currency syntax is three uppercase letters; the lab does not validate the currency's existence or independently check its exponent.

One obligation alias must persist across original and backup paths. Same payee and amount do not establish same obligation. Distinct aliases for a single real obligation hide its relationship from the lab; an incorrect merger can create false findings. Mapping requires operator review.

v0.1 represents a single full payment per obligation. Split payments, overpayment allowances, netting, refunds, FX, and remapped legal obligations are outside this contract.

## Exact action snapshot

Every decision and release contains an `action` with `obligation_id`, `attempt_id`, `route_id`, `amount_minor`, `currency`, and `payee_ref`.

A release is a distinct execution attempt at the boundary where an external payment effect can be created. It is not merely a draft, a UI click, a webhook delivery, or evidence that settlement occurred. Normalize ordinary duplicate log deliveries before review. Give distinct actual executions distinct attempt aliases. v0.1 does not infer provider idempotency from repeated transport requests.

## Decision

```json
{
  "type": "decision",
  "event_id": "event-004",
  "at": "2026-01-01T12:00:03Z",
  "decision_id": "decision-b",
  "decision": "HOLD",
  "action": {
    "obligation_id": "invoice-001",
    "attempt_id": "attempt-b",
    "route_id": "processor-b",
    "amount_minor": 125000,
    "currency": "USD",
    "payee_ref": "payee-001"
  }
}
```

The only decision values are `ACCEPT`, `HOLD`, and `REFUSE`. The lab checks an accepted action against prior supplied attempts and compares any linked release to its exact snapshot. A rejected changed proposal is not itself a control gap.

A release that links an older decision after a newer decision for the same attempt produces a superseded-decision finding. Reusing an earlier acceptance cannot hide a subsequently recorded refusal.

## Release

```json
{
  "type": "release",
  "event_id": "event-005",
  "at": "2026-01-01T12:00:04Z",
  "decision_id": "decision-b",
  "action": {
    "obligation_id": "invoice-001",
    "attempt_id": "attempt-b",
    "route_id": "processor-b",
    "amount_minor": 125000,
    "currency": "USD",
    "payee_ref": "payee-001"
  }
}
```

`decision_id` is optional for incomplete histories. An absent or uncaptured preceding decision is an evidence gap, not proof that approval was absent. A release linked to a captured HOLD/REFUSE decision is a control finding. A changed amount, currency, payee, route, obligation, or attempt relative to the linked decision is also a finding.

After a predecessor's supported final closure, a replacement must link to a decision recorded after that closure. An earlier approval remains stale even when it was issued before the original attempt released. Repeated records of the same supported closure do not invalidate an otherwise fresh decision. This chronology check does not infer a policy's expiration or revocation.

## Outcome and evidence

```json
{
  "type": "outcome",
  "event_id": "event-003",
  "at": "2026-01-01T12:00:02Z",
  "attempt_id": "attempt-a",
  "outcome": "closed_no_effect",
  "evidence": {
    "origin": "provider",
    "reference": "closure-evidence-a",
    "final": true
  }
}
```

| Outcome | Replay interpretation |
| --- | --- |
| `unknown` | The earlier attempt remains unresolved |
| `failed_nonfinal` | A provisional failure; the attempt remains unresolved |
| `completed` | A terminal completion assertion, requiring supported final evidence |
| `closed_no_effect` | A terminal assertion that the attempt cannot create a payment effect, requiring supported final evidence |

The evidence object is optional for incomplete histories. When present, its fields are `origin` (`provider`, `bank`, `operator`, or `synthetic`), a redacted `reference`, and boolean `final`.

The replay only treats a terminal claim as supported when `final` is true and origin is provider/bank, or synthetic in a synthetic trace. An operator note is not supported final evidence. Synthetic-origin evidence is not supported for `redacted_history`. Unknown and nonfinal failures never close an attempt, regardless of an evidence label. Contradictory later outcomes produce an evidence gap and retain uncertainty.

**These are labels supplied by the operator.** The lab does not fetch, verify, or authenticate evidence. Do not convert a transport error, cancellation request, timeout, or webhook name into final closure without independently establishing the provider's semantics.

## Chronology and limits

Timestamps use the supported RFC 3339 subset: `YYYY-MM-DDTHH:MM:SS`, optional one to six fractional digits, and `Z` or an explicit `+HH:MM`/`-HH:MM` timezone. Calendar dates, clock values, and timezone ranges must be valid; leap seconds are unsupported. Offsets are compared as instants. Events must be ordered; equal timestamps retain input order. The lab refuses an out-of-order file instead of sorting it into an apparently safe history. Resolve clock skew and causal ambiguity during normalization.

Event and decision aliases must be unique. Each attempt has one release record. An outcome without a captured release is an evidence gap. Each action must refer to a declared route and obligation. A declared obligation without any decision or release records is also an evidence gap.

Maximum input size is 2 MiB, 5,000 events, 1,000 obligations, 100 routes, and JSON nesting depth 32. HTML previews up to 200 timeline events and 200 findings per trace; JSON retains all reviewed records and findings. No files are uploaded.
