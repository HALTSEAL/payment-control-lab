# Interpreting the report

A trace review answers what the supplied records support, within declared paths and an operator's obligation mapping. It does not decide whether money may move now.

## Trace verdicts

| Verdict | Interpretation |
| --- | --- |
| CONTROL_GAP_OBSERVED | At least one captured decision or release conflicts with the declared diagnostic contract |
| INCONCLUSIVE | No supported control finding, but evidence is missing, inconsistent, or unsupported |
| NO_FINDING_IN_TRACE | No supported finding in the supplied records and declared scope |

When a finding and missing evidence coexist, the verdict is CONTROL_GAP_OBSERVED and the evidence-gap count remains visible. A finding does not erase a missing manual route. A finding count is not a count of monetary losses or independent incidents; one release can trigger more than one diagnostic finding.

NO_FINDING_IN_TRACE is not a production PASS, assurance opinion, independent audit, or certification. A short history cannot prove what an uncaptured path does. The “captured” route labels and final-evidence labels are supplied by the operator.

## Evidence and exactness

Unknown and failed_nonfinal outcomes retain unresolved status. Supported final closure can close an attempt for replay purposes. Completion is retained for the declared obligation. Conflicting later outcomes remain inconclusive and are not used as a basis for a favorable conclusion.

The lab compares a release with its recorded decision's exact action and checks overlapping attempts from the supplied chronology. It does not infer sender authority, signature validity, policy expiration, revocation, provider idempotency, or missing relationships between different obligation aliases.

Changed-action findings include the expected and recorded values. The JSON timeline retains the supplied event records so references can be inspected alongside the diagnosis. An older acceptance superseded by a newer decision for the same attempt cannot be used without a finding.

For replacement after a supported final closure, the linked decision must follow the predecessor's first supported closure record. An earlier approval is a finding even if no overlapping release occurred. `attempt_summary[].replay_status` describes the replay interpretation, not an authenticated provider outcome; an unsupported terminal claim remains unresolved.

An observed release while an earlier attempt is unresolved is a **risk finding**, not proof that both attempts settled. Completed outcomes are still operator-supplied assertions.

## CI use

Use `review` on normalized supplied records, `check-policy` on a trusted local function, or `compare-policy` on explicit before/after wrappers. Default `--ci-mode gate` exits 2 for findings/mismatches and 3 for incomplete evidence. Both require review. `--ci-mode report` returns process exit 0 for completed diagnostics while keeping those diagnostic exits, verdicts, and findings in the reports. Advisory completion is not approval. Invalid input, import, or output exits 1 in either mode and produces no new report; an older report is not evidence of the failed run.

Comparison runs both functions sequentially against the same absolute synthetic contract. No number of improvements cancels a regression or a remaining mismatch. A baseline error makes the comparison incomplete even when the candidate matches every expectation. Changes between HOLD and REFUSE are equivalent only in cases that explicitly allow both. Use deterministic wrappers and isolated test state; comparison does not fetch a previous Git revision or exercise distributed execution.

Do not use `demo` exit 0 as a payment gate. It means the intentionally mixed synthetic examples reproduced their expected diagnoses.

The function challenges include positive cases to avoid treating a policy that always refuses as useful. A fixture mismatch can be unnecessary refusal or unsafe acceptance. EXPECTATIONS_MET only establishes agreement with these 16 explicit synthetic contexts.

## Share with the workflow owner

Every completed diagnostic run writes `report.html`, `report.json`, and `owner-summary.html`. The JSON envelope uses report schema `0.2`; the input schema remains `0.1`. Its `owner_summary` retains full fields, including `local_follow_up`, `workflow_follow_up`, comparison, and CI metadata where applicable. Long fields are shortened in the compact HTML; use the full report and JSON for complete evidence.

The free follow-up is to fix code, correct mapping, add records, and rerun. Actual path coverage, authoritative evidence, and decision ownership need workflow evidence outside these synthetic checks. A paid assessment is optional help answering those questions, never required to inspect or fix a finding. See [CI adoption](ADOPT_IN_CI.md).

Report files are replaced as one staged bundle with rollback for ordinary write failures, not a transaction resilient to a machine crash.

Keep the result's limitations, input digest, scope, and source type attached. Share only redacted reports. State which original and backup paths are included, which records are missing, and which person decides whether to release again.

For a paid assessment, choose one workflow and one decision deadline. Review the evidence and the operational boundary before considering any enforcement deployment.
