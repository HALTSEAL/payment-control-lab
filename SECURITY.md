# Security and sensitive data

The bundled diagnostic commands read local JSON and write local HTML/JSON. They contain no payment provider adapters, credential handling, transaction signing, network requests, remote fonts, or telemetry.

`check-policy` and `compare-policy` explicitly import and execute trusted code supplied by the user. They are not sandboxes. A callback may have capabilities outside this project's control. Use a pure local decision function, never a payment execution function. Comparison wrappers run sequentially in one process; reset test state and mock dependencies explicitly.

## Handle input and output deliberately

- Use aliases for people, obligations, attempts, routes, and evidence references.
- Remove credentials, account numbers, personal data, raw provider responses, and customer secrets before creating an input file.
- Free-text workflow and route labels are not automatically redacted. The JSON report retains supplied event records. Review generated reports before sharing them.
- Input files are limited to 2 MiB, 5,000 events, 1,000 obligations, and 100 declared routes. Duplicate JSON keys, invalid numeric values, unexpected fields, ambiguous identifiers, and out-of-order timestamps are rejected.
- HTML is escaped and contains no JavaScript or external assets. The contact link opens the HALTSEAL website without uploading report contents.
- Final evidence is an operator assertion. Do not treat this tool as an evidence authenticator, live control, or security certification.

Report outputs replace existing `report.html`, `report.json`, and `owner-summary.html` in the selected directory. All three files are staged before replacement; a normal replacement failure rolls back files already changed. This is not a filesystem transaction across process termination. The tool refuses to overwrite its input file and refuses symbolic links or non-file targets for those output files. The report directory is assumed to be controlled by the person running the command.

Advisory CI mode preserves findings and diagnostic exit codes while allowing the diagnostic process to exit 0. It must not be interpreted as approval. Invalid input, imports, and output errors still fail. The customer CI example uploads report artifacts to GitHub; that transfer is separate from the local CLI's no-upload behavior. Agree artifact access and retention, use read-only PR permissions, and never supply production credentials to an adapter or execute untrusted PR code through a privileged workflow.

## Report a problem

Do not place sensitive records or exploitation details in a public issue. Use [HALTSEAL Contact](https://haltseal.com/contact/) to request a private security discussion. Keep the initial message limited to the affected lab version and a general description, with no customer secrets.
