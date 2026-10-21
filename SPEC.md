# Workflow migration frequency review — specification

## Purpose and policy

Implement the [assignment](_data/assignment.md): turn incomplete ETL run history and user feedback into an auditable frequency decision for every workflow. The fastest recurring scheduled cadence must be **hourly or less frequent (≥60 minutes)** to qualify. Execution success is separate from frequency eligibility; workflow names are not schedule evidence.

| Outcome | Definition |
| --- | --- |
| MIGRATE | Evidence supports hourly-or-slower scheduling with no unresolved eligibility issue. |
| TO ENGINEER | Recurring sub-hourly scheduling, or eligibility still unresolved after completed agent review. State the investigation needed. |
| UNKNOWN | Python cannot determine cadence/current eligibility, or agent review is pending, skipped, failed or invalid. Completed unresolved reviews become TO ENGINEER. |
| DO NOT MIGRATE | A human explicitly records retirement or exclusion with a reason. Silence or failures alone are insufficient. |

## Two-step pipeline and human review

1. **Python:** read `_data/run_history.csv`, validate and account for every row, group supported retries, and compare interval, clock-slot and calendar candidates. Write `dist/step1_results.csv` with flow ID, observation window, cadence, provisional outcome, explanation and source references. Preserve raw attempts and data issues separately. Missing end times are valid; invalid starts and insufficient evidence remain visible.
2. **Agent:** review the step 1 CSV, all raw attempts and `_data/feedback.md`. Validate one response per workflow and its evidence references. Write `dist/step2_results.csv` retaining step 1 fields and adding the reviewed outcome, cadence, next action, evidence, **why this outcome fits**, and **why it agrees with or changes Python**. Unchanged outcomes still require human-readable explanations.
3. **Human correction:** inspect/filter the HTML dashboard and save an outcome, cadence, reviewer name and reason. Append to `_data/overrides.json`; the latest active correction controls the effective decision and receives a **User override** tag. Removing a correction restores the previous active correction or automated result while preserving history.

Each run locks, cleans and rebuilds `dist/`, including both CSVs, dashboard, evidence, feedback snapshot, agent artifacts and manifest. Inputs, corrections and logs persist. Failed/skipped agent reviews produce fresh, visibly incomplete UNKNOWN automated results. Saved human corrections remain distinguishable. The dashboard uses the whole file’s date range, status-colored runs, hover details and source attempts with execution time, gap and overlap.

## Good and bad outputs

| Evidence | Good output | Bad output |
| --- | --- | --- |
| `wf_SLS_ORDERS_INCR`: daily starts plus supported failure retries | Daily → MIGRATE; explain retry grouping. | Use the shortest retry gap as cadence. |
| `wf_WEB_CLICKS`: hourly slots with jitter and missing ends | Hourly → MIGRATE; cite alignment. | Treat a 52-minute gap as a faster schedule. |
| `wf_FIN_BUDGET_ACTUALS`: July 3, August 5, September 3 near 06:00 | Monthly, third Monday–Friday day → MIGRATE. | Infer holidays or require 90 days of runs. |
| `wf_PAY_AUTH_HOURLY`: repeated 30-minute starts | TO ENGINEER; name is misleading. | MIGRATE because the name says hourly. |
| `wf_FIN_QTR_REG_RPT`: one start | Python UNKNOWN → agent TO ENGINEER; request schedule configuration. | Claim quarterly recurrence from one observation. |
| `wf_MKT_CAMPAIGNS`: unexplained trailing inactivity | Request current schedule/retirement confirmation. | Automatically mark DO NOT MIGRATE. |

## Definition of done and limits

A clean run accounts for every workflow, produces both CSVs and a usable dashboard, validates review references, explains changed and unchanged outcomes, and distinguishes incomplete automation from approval. Corrections survive reruns. Automated tests cover cadence families, rejection cases, recovery detection, review failures and artifact lifecycle; UI checks cover filtering, evidence, exports and corrections.

The prototype does not execute migrations or authenticate reviewers. Missing history, holidays and changing schedules can still require investigation. See [README](README.md) for operation and [the detailed contract](docs/PIPELINE.md) for thresholds, fields and further acceptance examples.
