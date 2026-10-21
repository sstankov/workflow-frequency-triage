# Submission review — 2026-10-21

Reviewed against the [assignment](../_data/assignment.md). The submission includes source inputs, prototype, completed outputs, documentation, prompts and public conversation logs.

| Assignment requirement | Evidence |
| --- | --- |
| One-page spec, definition of done, at least three good/bad examples | [SPEC.md](../SPEC.md): concise overview, six paired examples and completion criteria. Detailed rules are separate in [PIPELINE.md](PIPELINE.md). |
| Working frequency/eligibility prototype with human correction | [CLI](../pipeline.py), [dashboard](../dist/index.html), [source](../workflow_triage/) and persistent correction service; correction saving/removal tested through local HTTP. |
| Prompts/conversations and time spent | [Review instructions](../prompts/review.txt), [exact run prompt](../dist/agent_prompt.txt), [public logs](../logs/) and the elapsed-time statement in [README](../README.md). |
| Short README: run, assumptions, omissions, likely errors and AI mistake | [README.md](../README.md), including a no-model preview path for supplied outputs. |

## Output verification

The included [manifest](../dist/manifest.json) records completed run `d7fc7c86-a57d-4ad6-a608-11074a2f2d2a`, rule/prompt versions 3.1 and runtime 238.95 seconds. There are **1,152 source attempts, 40 workflows, 30 MIGRATE and 10 TO ENGINEER**, with 7 changes from Python and no incomplete reviews or applied human overrides.

- Source CSV, feedback and prompt hashes match the manifest.
- Current Python analysis reproduces step 1 and its evidence. The archived real agent response passes current validation and reproduces step 2/results; both CSVs match exactly.
- The archived prompt/schema, reviewed feedback snapshot and generated HTML match current inputs/contracts/template. JSON object-key order is preserved from archived evidence for exact text comparisons.
- The linked pipeline log contains the full prompt and public outcome explanations. Historical failure logs remain as traceability; the manifest identifies the completed run to review.
- `dist/` contains only the eleven pipeline artifacts. Check screenshots live in `logs/`, not `dist/`.

No new model review was invoked for this audit: the real completed review remains valid for the unchanged inference inputs/policy. Reconstructing its outputs for verification is not represented as a new review.

## Verification performed

`python3 -m unittest discover -s tests -v`: **48 tests pass**. Coverage includes cadence families and delayed-recovery rejection cases, review failures, clean output rebuilding, retained corrections, correction removal, HTTP origin checks, escaping and repository isolation.

Browser inspection confirmed outcome-card filtering (10 engineer results), workflow evidence, the shared 90-date activity range, stopped-run details, two-unit durations, overlap filtering (2 of 90 runs for `wf_DIM_CUSTOMER`) and the correction form. Save/remove behavior was exercised by automated HTTP integration tests in isolated temporary repositories; the supplied final decisions were not edited for testing.

Maintained Markdown links/formatting and CLI options were checked. A common credential-pattern scan found no matches; this is a bounded check, not a guarantee that arbitrary secret formats are absent. Original inputs and append-only historical logs were preserved.

## Time and packaging

The author confirmed using the first log as the start point: **2026-10-21 15:29:14 +0300**. At **2026-10-21 17:27:36 +0300**, elapsed time was approximately **1h 58m**, including model execution and waiting. Initial log entries were backfilled when logging was introduced, so this is the agreed logged-session estimate rather than an independently timed active-work measure.

The submission ZIP is built from the complete working directory, including untracked source, tests, documentation, outputs and logs. It excludes Git internals, Python caches, the runtime lock and macOS metadata. A per-file SHA-256 inventory inside the archive allows integrity checks after extraction. Git currently tracks the input files only; a repository-only handoff requires committing the remaining project files. The ZIP includes them without changing Git history or publishing anything externally.

Packaging verification: the ZIP was extracted into a clean temporary folder, all 63 packaged file hashes and ZIP integrity passed, and all 48 tests passed again in 3.612 seconds. CLI help also passed from the extraction. Live CSV download endpoints and the manifest matched the supplied files. Final packaging updates only these documentation/log notes; the tested source, inputs and output artifacts are unchanged.

To review the supplied result, extract the archive, enter its `workflow-frequency-triage/` folder and run `python3 pipeline.py serve`. To reproduce a fresh model review, use `python3 pipeline.py run` with a signed-in Codex CLI. A new review can vary; the supplied run is the auditable submission snapshot.
