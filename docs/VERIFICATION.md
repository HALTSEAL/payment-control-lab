# v0.2.0 verification record

Local verification on October 3, 2026 used Python 3.12.14 on Linux. These checks establish the lab's behavior against its authored inputs and expectations. They do not establish production payment protection or independent customer reproduction.

| Check | Result |
| --- | --- |
| Private development regression suite | 147 tests passed, including distribution, artifact-integrity, fresh-history and current-owner publication regressions |
| Reviewed diagnostic source ZIP | 59 diagnostic files; private preparation records excluded; all 110 bundled diagnostic regressions passed in the fresh installation environment; local documentation links resolve inside the ZIP |
| Bundled trace demonstration | 16 of 16 expected diagnoses reproduced |
| Stateless example function | 16 of 16 independent expectations matched |
| Deliberately limited per-route example | Cross-route mismatches reported with exit 2 |
| Isolated wheel installation | Console and module entrypoints worked outside the checkout |
| Reviewed release wheel | Built in an empty directory from the reviewed ZIP; all 29 runtime files and the included status notice matched source hashes; every wheel RECORD entry verified |
| Disclosure boundary regression | Untracked-package and stale-build probes excluded; two repeated wheel builds with the same backend were byte-for-byte equal |
| Wheel resources | 29 packaged module/data files matched the tested source, including all 16 traces and the owner-summary module |
| Diagnostic exit codes | Findings 2; incomplete evidence 3; no finding 0; invalid input 1 |
| Before/after comparison | Repaired candidate: 11 improved, zero regressed, expectations met; reverse change: 11 regressed, exit 2 |
| CI modes | Advisory results retain mismatches and unknowns; default gate retains exits 2/3; configuration and output failures retain exit 1 |
| Customer adapter | An unbound adapter stays inconclusive in both modes; a customer's module loads from its application root outside the lab checkout |
| Customer CI template | Diagnostic and job-summary steps replayed locally for matching, mismatched, unbound, gate, invalid-import, and regressed-comparison cases; stale reports cleared |
| Report rendering | Full report and owner brief for nine results checked at 1440, 720, 390, and 320 CSS pixels: 72 screen/print layout checks |
| Report interaction and privacy | Keyboard disclosures worked; no document overflow, page errors, scripts, or external asset requests |
| Print layout | No document overflow in the same four layouts; nine owner briefs each rendered to one A4 page |
| Report bundle | Deterministic HTML/JSON/owner brief; output protection and ordinary write-failure rollback verified for all three files |

Browser checks used Chromium 153.0.8010.0. The owner brief and comparison report were also visually inspected at desktop and mobile widths. These are local checks, not a claim that every browser or device has been tested. Compact HTML truncates long labels; JSON retains the complete fields. One-page rendering of these nine bounded examples does not guarantee one-page output for arbitrary future inputs.

The customer CI exercise replayed its diagnostic and job-summary commands from a separate application root. It did not install a workflow in a customer's repository, test a private cross-repository checkout, or upload artifacts to GitHub. The template's reviewed-commit placeholder must be configured before adoption.

## Current publication candidate checks

The separate publication preview retains 70 repository files: 59 diagnostic paths, LICENSE/NOTICE proposals and nine public development files. Its curated source ZIP contains 61 paths. The preview reproduces 135 public-repository regressions, has one initial main commit, and imports no predecessor refs, configured remotes, host templates or shared Git objects. Preparing those files does not apply the license or publish a repository.

The trusted release manifest now binds the complete source ZIP and wheel SHA-256, alongside their source-file and runtime inventories. The independent verifier rejects replacement assets even if side checksums are recomputed, as well as unsafe paths, extra files, duplicate records and unexpected dependencies. Its public regression suite exercises that boundary. Verify four downloaded assets from a trusted checkout before installation; obtain the manifest digest from the trusted Release record.

The latest byte-pinned standalone and shared-shell developer candidates passed eight layouts each, with mobile, light/dark, print, enlarged text, keyboard and no-script checks. The website integrity verifier passed 3,039 checks; its exact approved public build remained unchanged. The website's own inspected hosted jobs ended without runner assignment or executed steps. The pinned browser checks also run in the lab's actual hosted workflow; read its result at the final source commit.

The HALTSEAL-branded first launch now supports a confirmed current owner or authorized publisher, with formation/assignment evidence required only for the new-assignee route. Mechanical fixtures verified direct-owner export without formation or an assignment, and verified that a separate publisher still needs copyright authority. Exact owner/publisher identities are bound to the Work schedule; named previews remain unlicensed. These fixtures are not actual rights evidence.

Actual copyright/publication authority, public repository access, a GitHub Release and anonymous download/installation remain unconfirmed. HALTSEAL Inc. formation is a separate workstream. The default clean preview remains an unapplied private licensing draft, and public-license mode must refuse it. These checks do not establish production payment protection.

## Reproduce the core checks

```sh
python -m unittest discover -v
python lab.py demo
python lab.py check-policy examples.fixture_policy:decide
python lab.py compare-policy examples.route_retry_policy:decide examples.fixture_policy:decide
python lab.py check-policy examples.customer_adapter:decide --ci-mode report
```

The deliberately limited function is expected to exit 2:

```sh
python lab.py check-policy examples.route_retry_policy:decide
```

Build a wheel, install it into a fresh virtual environment, change to a directory outside the checkout, then run `payment-control-lab demo` and `python -I -m payment_control_lab demo`. This checks that bundled resources and entrypoints work without the source directory on the import path.

The GitHub workflow configures Python 3.11–3.14 on Linux and Python 3.12 on Windows. Its live Actions status is separate from this local verification record; do not infer that a hosted job ran from the presence of its YAML file.

## Hosted browser and platform verification

The Python matrix runs on Linux 3.11–3.14 and Windows 3.12. A separate development-only Chromium job reruns nine diagnostic results and their owner briefs at four widths: 72 screen/print layout combinations, keyboard disclosure/table checks, no scripts or external asset requests, and nine one-page A4 owner summaries. Synthetic screenshots, PDFs, and verification.json are retained as a GitHub artifact.

Read the [live Actions result](https://github.com/HALTSEAL/payment-control-lab/actions) for the exact commit. Local checks, hosted execution, and external customer reproduction are separate evidence categories. Browser tooling is installed only for development verification; users of the offline Python CLI do not need it.

## Public-release preparation verification

On October 3, 2026 the predecessor main commit [`728be69`](https://github.com/HALTSEAL/payment-control-lab/commit/728be69f057d09f4e2c35871c3a1fd8d85a8842d) passed all six [platform/report jobs](https://github.com/HALTSEAL/payment-control-lab/actions/runs/37140810002) and the [release-candidate job](https://github.com/HALTSEAL/payment-control-lab/actions/runs/37140809937). That hosted browser job also checked the pinned standalone website candidate from website main `09c9175`. These are actual hosted results, distinct from the local package-scope changes above. Read the live Actions result for the final commit before distributing it. A candidate artifact is not a public Release; licensing, Git-history review and anonymous access remain separate.

The website's own Quality and Live Edge jobs for `09c9175` ended without a runner assignment or any executed step. They are not recorded as passed. Its standalone/shared-shell developer candidate passed 16 local screen/print/enlarged-text layouts, theme controls, keyboard and no-script checks. The website route is still staged; those checks do not establish public deployment.
