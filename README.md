# Workflow frequency triage

A local prototype for the [assignment](_data/assignment.md): review incomplete ETL run history, identify workflows eligible for migration, and let a human correct the result. **Hourly or less frequent schedules qualify; faster or unresolved schedules go to an engineer.** This tool assesses frequency eligibility; it does not execute migrations.

## Run locally

Requires Python 3.9+ on macOS/Linux and an installed, signed-in Codex CLI (`codex login`). Python uses only the standard library. Agent review uses the CLI’s configured model and account usage.

From the repository root:

```sh
python3 pipeline.py run
python3 pipeline.py serve
```

The included outputs are already reviewed: run only `python3 pipeline.py serve` to inspect them without invoking a model. Open [the dashboard](http://127.0.0.1:8765). Stop the server with Ctrl+C. Opening `dist/index.html` directly supports inspection; saving corrections requires the local server.

Inputs are [_data/run_history.csv](_data/run_history.csv) and [_data/feedback.md](_data/feedback.md). The CSV requires `workflow_name`, `start_time`, `end_time` and `status`; end times may be blank. Include `_data/` when sharing the repository or submission archive.

**Every run deletes and recreates the entire `dist/` directory.** Inputs, saved corrections and append-only logs persist. Keep hand-maintained files outside `dist/`.

## Review a workflow

1. Python validates attempts, infers cadence and writes `dist/step1_results.csv`.
2. A Codex agent reviews that CSV, raw attempts and feedback. Its validated response becomes `dist/step2_results.csv`, with evidence and explanations of both the outcome and why it agrees with or changes Python.
3. Use ALL/outcome cards and search to find a workflow. Inspect its decision, status-colored activity chart, run history and automated comparison. Save an outcome, cadence, reviewer name and reason under **Corrections & history**. Every saved correction gets a **User override** tag and persists in `_data/overrides.json` across reruns.

| Outcome | Meaning |
| --- | --- |
| MIGRATE | Evidence supports hourly-or-slower scheduling. |
| TO ENGINEER | Faster scheduling, or eligibility remains unresolved after agent review. |
| UNKNOWN | Python cannot resolve eligibility, or the agent review is incomplete. |
| DO NOT MIGRATE | A human explicitly confirms exclusion or retirement with a reason. |

The latest active human correction determines the effective decision. **Remove correction** keeps the record and removal audit, restoring the previous active correction or automated decision. Both automated decisions and correction history remain available. Reviewer names are self-reported, not authenticated.

## Outputs and verification

All generated artifacts are in `dist/`: both CSVs, `index.html`, `results.json`, `evidence.json`, `data_issues.json`, the reviewed `feedback.md` snapshot, agent prompt/schema/response, and `manifest.json`. The response file exists only when a response was returned. Check the manifest’s state and each result’s `review_complete` and `decision_source`; an outcome alone does not prove automation finished.

```sh
python3 -m unittest discover -s tests -v
python3 pipeline.py run --timeout 1200
# Development only: rebuilds outputs with incomplete UNKNOWN automated results.
python3 pipeline.py run --skip-agent
```

The default agent timeout is 600 seconds. Tests use temporary repositories and test reviewers, without model usage. A failed agent review produces incomplete outputs and exits nonzero; intentional `--skip-agent` exits successfully. Fatal input errors produce a failed manifest/dashboard.

## Assumptions, omissions and likely errors

- Starts determine cadence; workflow names and execution failures do not. Short retention can suffice. Monthly positions count Monday–Friday without inferring holidays.
- Timestamps have no timezone; timezone-aware inputs require normalization. The latest start in the file approximates the export boundary.
- Missing history can hide faster schedules. Retry grouping, hourly jitter tolerance, changing schedules and holiday/month-boundary shifts are the most likely sources of mistakes. Alternative matches are exposed; finite history cannot prove a unique scheduler configuration.
- Agent validation checks structure and policy consistency, not the truth of every assertion. MIGRATE does not certify operational readiness. There is no scheduler integration, migration execution, external database or authentication.

An early AI-authored rule mistook failure retries on a daily order workflow for hourly scheduling. Repeated sub-daily evidence is now required across multiple dates, with regression coverage. A separate missed retry crossing midnight was also fixed and tested.

## Assignment deliverables and agent guidance

- [SPEC.md](SPEC.md): one-page policy, definition of done, and good/bad examples.
- [Detailed pipeline contract](docs/PIPELINE.md): cadence rules, CSV fields, failure handling and dashboard behavior.
- [Development guide](docs/DEVELOPMENT.md) and [AGENTS.md](AGENTS.md): architecture, verification and instructions for coding agents.
- [Review prompt](prompts/review.txt) and [logs](logs/): prompts, public responses and verification history. Hidden model reasoning is excluded; secrets are redacted.

Time spent: approximately **1h 58m elapsed**, from the [first recorded log](logs/2026-10-21-01a15e6e-5bad-7d03-a5e6-f1f9ad4695c4.md) at 2026-10-21 15:29:14 +0300 through the submission review at 2026-10-21 17:27:36 +0300, using the start point confirmed by the author. This includes agent execution and waiting; it is not a separately measured active-work total. The completed [pipeline run](logs/2026-10-21-pipeline-d7fc7c86-a57d-4ad6-a608-11074a2f2d2a.md) took **238.95 seconds**. See the [submission review](docs/SUBMISSION.md) for verification and artifact details.
