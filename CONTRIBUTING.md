# Contributing

Intentional contributions for inclusion are governed by Apache-2.0 section 5 unless explicitly stated otherwise. Confirm your authority to contribute; changes to execution control, permit verification or other patent-relevant mechanisms require review of the exact change. This document does not request a separate copyright or patent assignment.

For authorized development, prioritize independently reproducible payment-control cases, input-mapping improvements, and clear operator reports.

1. Start with a redacted synthetic case and a concrete expected finding or evidence gap.
2. State the evidence assumptions, covered paths, and what cannot be inferred.
3. Keep provider status mappings separate from claims of authoritative finality.
4. Run `python -m unittest discover -v` and the direct `python lab.py demo` quickstart.
5. Include the effect on valid payments as well as risky replacements. An always-refuse policy is not a useful acceptance model.

Do not submit customer records, credentials, production control code, proprietary kernel material, invented integration support, or unverified certification claims. A new provider example must be explicitly labeled synthetic unless an actual adapter and its supported semantics have been validated.

Keep runtime dependencies at zero unless a demonstrated workflow need justifies changing the v0.2 distribution contract.
