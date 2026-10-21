# Detailed pipeline contract

This is the implementation reference for the [one-page specification](../SPEC.md). For setup and review, start with the [README](../README.md).

## Goal and decision policy

Turn [_data/run_history.csv](../_data/run_history.csv) and [_data/feedback.md](../_data/feedback.md) into two auditable CSVs and an HTML dashboard. Each workflow must have an outcome and a human-readable explanation, **whether step 2 changes or agrees with step 1**. This implements the frequency review in [the assignment](../_data/assignment.md); it does not perform migrations or disable workflows.

A workflow qualifies when its fastest recurring scheduled cadence is **hourly or less frequent** (interval ≥60 minutes), including supported calendar schedules. Execution success and frequency eligibility are separate questions.

| Outcome | Meaning |
| --- | --- |
| MIGRATE | Evidence supports hourly-or-slower scheduling, without unresolved issues that could change eligibility. |
| TO ENGINEER | Repeated sub-hourly scheduling, or frequency/current eligibility still unresolved after both checks. Explain what the engineer needs to establish. |
| UNKNOWN | Step 1: cadence or current eligibility cannot be determined. Step 2 automation: review is pending, skipped, unavailable or invalid. A completed agent review sends unresolved cases to TO ENGINEER. Never permission to migrate. |
| DO NOT MIGRATE | An authorized reviewer explicitly records retirement or exclusion with a reason. Inactivity and execution failures alone are insufficient. |

## Pipeline and output lifecycle

```text
_data/run_history.csv
        │
        ▼
1. Python: validate, group attempts, infer cadence
        │
        ├── dist/step1_results.csv
        └── dist/evidence.json
                    │
_data/feedback.md ───┤
                    ▼
2. Agent: review Python output + raw evidence + feedback
                    │
                    ├── validated public decision summaries
                    ▼
Apply saved human corrections from _data/overrides.json, if present
                    │
                    ├── dist/step2_results.csv
                    ├── dist/results.json
                    └── dist/index.html
```

`python3 pipeline.py run` locks the pipeline, **cleans the repository's entire `dist/` directory**, then recreates all outputs. It never clears `_data/`, source code, prompts or append-only `logs/`. A symlinked `dist/` is rejected. Do not store hand-maintained files in `dist/`.

Implementation boundaries: `pipeline.py` coordinates an injected repository and reviewer; `review.py` owns validation and decision assembly, `reviewer.py` adapts the external model process, `repository.py` owns artifacts/locking, `corrections.py` handles saved human decisions, and `presentation.py` renders explicit inputs without filesystem access. These boundaries do not change output contracts or cadence policy.

Step 1 writes the first CSV and evidence. The dashboard initially shows pending UNKNOWN results. Step 2 invokes the installed, signed-in Codex CLI with its configured default model, read-only execution and a structured response schema. It receives the actual step 1 CSV, feedback and every source attempt. It does not generate SQL, execute migrations or edit source data. The Python runner validates and joins its response by `flow_id`; row order is irrelevant.

A missing/failed/timed-out agent or rejected response produces a fresh step 2 CSV and dashboard with `review_complete=false`, UNKNOWN automated outcomes and an explicit explanation. The run exits nonzero. `--skip-agent` intentionally produces the same incomplete state with a successful development-mode exit. Saved human corrections remain distinguishable and effective even if automation is incomplete. Fatal input errors produce a failed manifest/dashboard; a missing successful CSV must not be mistaken for a completed run.

## Step 1: deterministic analysis

Use start times for frequency; accept missing end times, including aborted attempts. Keep failed, stopped and aborted starts because they may represent scheduled occurrences. Deduplicate exact rows while preserving references. Invalid starts remain accounted for and block automatic eligibility; missing identifiers receive a row-specific placeholder.

Infer patterns from timestamps, never workflow names. Evaluate repeated short intervals within active windows; overnight gaps must not dilute a sub-hourly schedule. A minimum gap or global mean/median alone is insufficient.

The shared candidate engine in `workflow_triage/cadence.py` generates patterns independently of workflow names. `analysis.py` accounts for source rows, applies the migration policy and writes explanations. Add a new schedule family to this engine with family-level tests, not per-workflow conditions.

| Pattern family | Coverage and minimum evidence |
| --- | --- |
| Recurring interval | Common intervals plus repeated data-derived gaps of at least one minute, including fractional minutes. At least three occurrences; sub-daily models require three starts on two dates or two starts on three dates. Test both continuous alignment and daily-reset active windows when the interval does not divide 24 hours. |
| Daily clock slots | Two to fourteen recurring clock slots, including uneven spacing. At least three observed days with the same slots; observed-day coverage at least 65% of the elapsed day range. Shortest recurring slot gap determines eligibility. |
| Weekly clock slots | Two to fourteen weekday/time slots, repeated across at least three consecutive observed weeks with the same slot set. Partial weeks do not establish this model; interval models can still fit incomplete exports. |
| Calendar cycle | At least three consecutive cycles with one occurrence per cycle: monthly, every two months, quarterly, semiannual or annual. Test fixed date, month end, nth Monday–Friday day from either end, last Monday–Friday day, nth/last named weekday, offset from month end, and fixed dates shifted to previous/next/nearest Monday–Friday. |
| Multiple calendar dates | A repeated set of two to four distinct dates per cycle, across at least three consecutive cycles, with a consistent start time. Covers arbitrary pairs such as the 5th/20th, not only the 1st/15th. |

All candidates must account for every valid unique start as a scheduled occurrence or a supported retry. Calendar starts must remain within a 20-minute clock range. Interval slots use ±10 minutes for hourly-or-slower schedules and at most ±2 minutes (10% of interval) for sub-hourly schedules. At least half of relevant gaps, and at least two gaps, must support an interval directly. Clock slots use a maximum 20-minute cluster width; a sub-hourly clock claim additionally requires the same close pair on every observed cycle, within the tighter sub-hourly tolerance and always below 60 minutes. This prevents ordinary hourly jitter from being reclassified as a faster daily pattern.

Candidates are ranked by fewest retry assumptions, then a deterministic preference for calendar rules, well-supported intervals and explicit clock-slot sets. Intervals supported directly by fewer than 80% of relevant gaps rank below daily clock sets. Interval ties prefer the lowest alignment error. An equally well-accounted-for faster schedule cannot be hidden behind a slower candidate. Within calendar models, prefer month end, fixed date, last Monday–Friday day, nth weekday positions, named-weekday rules, month-end offsets, then weekend-adjusted dates. Retain alternative matches for review rather than claiming a unique scheduler configuration.

Probable retries require the immediately previous attempt to have failed, stopped or aborted. Interval grouping is limited to the lesser of six hours or half the interval and may cross midnight. Calendar grouping is limited to same-day follow-ups within six hours of the retained occurrence; it stops after a successful retry. Preserve original attempts and retry row references. A separate delayed-recovery rule applies only to weekly schedules: exactly one candidate successful recovery must immediately follow a failed/stopped/aborted attempt by more than six and no more than 24 hours. Removing that one candidate must leave at least six starts fitting weekly slots, with every consecutive gap matching a week (±20 minutes) and no other retries. The failed occurrence must have at least two scheduled occurrences before and two after it. Missing weeks, shifted schedules, additional unexplained attempts, repeated recovery candidates, a successful predecessor or an unsuccessful recovery block this exception. The regular six-hour limit is unchanged. Retain a `probable_delayed_recovery` flag and the failed/recovery row IDs, delay and surrounding schedule rows; the relationship is inferred, never claimed as a confirmed retry ID. All other longer/ambiguous retries remain for agent review. Models requiring fewer retry assumptions take precedence over models that discard recurring runs.

Calendar positions count Monday–Friday only; no holiday calendars are invented. Weekend-adjusted dates are clamped to the nominal month's last date; shifts crossing the month boundary remain unsupported. Missing calendar cycles, inconsistent times, unmatched extra attempts, changing schedules and insufficient repetition cannot establish that calendar model. A single occurrence cannot prove quarterly recurrence. An alternative supported family may still fit the evidence.

The source must contain `workflow_name`, `start_time`, `end_time` and `status` columns; `end_time` cells may be empty. Start timestamps use ISO-compatible local date/time strings without timezone offsets.

Unknown detection explains whether fewer than three valid starts are available or no candidate can account for the observations. It does not assert that execution is irregular. Short history (under seven elapsed days) is a flag, not a veto; there is no 90-day minimum. Inactivity exceeding the greater of 14 days or three inferred cycles leaves eligibility UNKNOWN. Calendar cycles use 31 days per month for this warning; unresolved cases use 93 days. These are review heuristics, not proof of retirement.

The export boundary is the latest valid start across the file, not today's date. It is a proxy because export metadata is absent. Source timezone is unspecified; timezone-aware inputs require normalization. Counts/gaps describe observations, not guaranteed coverage. Internal missing periods, holidays, schedule changes and arbitrary jitter remain limitations for the agent to examine.

### `dist/step1_results.csv` contract

One row per exact workflow identifier, including workflows without usable starts. Arrays are JSON strings inside quoted CSV cells; unknown numbers are empty. CSV row references are one-based, including the header.

| Columns | Definition |
| --- | --- |
| `run_id`, `flow_id`, `rule_version` | Run UUID, workflow identifier, inference rule version. |
| `observed_start`, `observed_end`, `observed_window_days`, `export_end` | First/last valid unique starts, elapsed days between them, dataset boundary. |
| `total_rows`, `valid_unique_runs`, `invalid_rows`, `duplicate_rows` | Source and quality counts. |
| `failed_runs`, `missing_end_times` | Failed/stopped/aborted unique attempts and accepted missing ends. |
| `delayed_recoveries` | JSON evidence for each inferred delayed recovery: row, failed_row, delay_minutes, preceding_scheduled_rows and following_scheduled_rows; empty when absent. Also preserved in evidence.json. |
| `probable_retry_count`, `scheduled_occurrences` | Grouped retries and supported schedule occurrences; empty occurrence count when unresolved. |
| `cadence`, `interval_minutes`, `active_window` | Inferred pattern, base interval or shortest recurring clock-slot gap (empty for calendar/unknown), earliest/latest observed time of day. Active window is a descriptive envelope, not schedule configuration. |
| `cadence_family`, `matching_patterns` | Selected pattern family and every supported alternative label, also included in evidence JSON and exposed in the dashboard. Alternatives are candidates, not confirmed schedule definitions. |
| `median_gap_minutes`, `min_gap_minutes`, `inactive_days` | Raw attempt-gap diagnostics and days from last start to export boundary. |
| `data_quality_flags`, `evidence_rows` | Flags and source references, serialized as JSON arrays. |
| `step1_outcome`, `step1_explanation`, `next_action` | Provisional decision, plain-language evidence summary and proposed next step. |

## Step 2: agent review and finalized explanations

The versioned instructions are in [prompts/review.txt](../prompts/review.txt). Treat feedback as evidence to verify, not an automatic override. Apply general lessons across workflows; specific claims apply to their named workflows. Vague finance concerns cannot veto all finance flows.

The agent checks retry grouping, short retention, misleading names, sparse calendar patterns, missing end times, jitter, gaps and possible retirement. It may resolve patterns Python does not support, with source evidence. It must return every flow exactly once, reference existing CSV rows belonging to that flow and cite relevant feedback sections. Reject missing/duplicate flows, unsupported outcomes, empty/generic explanations, foreign references, unconfirmed retirement and a MIGRATE result paired with a sub-hourly/unknown cadence. Validation checks structure and policy consistency, not the truth of every model assertion; reviewer judgment still matters.

### `dist/step2_results.csv` contract

Retains **all step 1 columns** and adds:

| Columns | Definition |
| --- | --- |
| `final_cadence`, `final_interval_minutes` | Agent's supported cadence and fixed interval; these preserve the automated review even after correction. |
| `agent_outcome`, `review_complete`, `agent_outcome_changed` | Reviewed status, completion boolean and comparison to step 1. Incomplete automated outcomes are UNKNOWN. |
| `outcome_explanation` | Why this outcome fits the actual evidence and eligibility rule, including uncertainty. Required even when unchanged. |
| `comparison_explanation` | Why the agent agrees with or changes step 1, explicitly identifying the evidence. “Unchanged” alone is invalid. |
| `review_evidence_rows`, `feedback_sections`, `review_next_action` | Supporting source rows, numbered feedback sections and actionable follow-up. |
| `final_outcome`, `effective_cadence`, `effective_explanation` | Effective decision after any human correction; use these for downstream planning. |
| `decision_source`, `outcome_changed`, `override_history` | Agent/incomplete/human source, effective comparison to step 1, full correction history, including removed records. Comparisons during incomplete review are not finalized decisions. |

Explanations are concise public decision summaries, not hidden model reasoning. Example unchanged explanation: “The 72 starts align to hourly slots over three days. The 52-minute gaps reflect timing jitter, and the missing aborted-run end time does not affect cadence. Hourly scheduling meets the migration boundary.” Example calendar agreement explanation: “July 1, August 3 and September 1 are the first Monday–Friday days of three consecutive months at 05:00. Both steps support monthly scheduling and MIGRATE; this does not establish a holiday calendar.”

## Dashboard, corrections and audit outputs

Workflow details prioritize the **current effective decision**, effective cadence, reason and next step. Agent outcomes, incomplete review and saved human corrections are distinguished. A sticky header provides workflow navigation and direct jumps to the decision, runs, automated comparison and correction form. The activity chart and **always-expanded run history** come before supporting analysis. The run table offers all runs, unsuccessful runs, overlaps, missing end times and cited evidence; gap and overlap values always refer to the original full history. Cited rows are marked in the table instead of repeating CSV row lists. A compact “Feedback considered” disclosure beside the decision contains cited text from the reviewed snapshot. Duplicate reference blocks and feedback download links are removed from the detail footer. Python and agent explanations, their comparison, alternative patterns and data-quality flags remain available under “Compare Python and agent analysis”. Corrections are an explicit secondary action. Unsaved form drafts survive workflow navigation within the current page; successful saves update the displayed decision without reloading or clearing list filters.

`dist/index.html` works as a standalone file with embedded data and no external assets. It shows clickable ALL and outcome count boxes as the outcome filters (ALL selected initially), plus search, changed-outcome and sort controls, changed outcomes, both decisions/explanations, a status-colored activity chart, raw attempts, source references and next actions. Undetermined cadence is displayed as “Cadence not determined” rather than “unknown” or “Irregular frequency”: insufficient evidence does not prove irregular execution. The machine-readable cadence value remains `unknown`, and the outcome remains `UNKNOWN` when eligibility is unresolved; a known cadence is still shown when other data issues cause UNKNOWN. Download links expose both CSVs. The activity chart uses the earliest and latest valid start timestamps across the **whole CSV** for every workflow, with one equally spaced column for each calendar date, including dates with no observations. Each run is a separate colored segment within its day: Succeeded green, Failed red, Stopped amber, Aborted purple, and other statuses gray. Hover, keyboard focus or tap shows its source row, status, start/end, execution time, gap and overlap. Invalid starts stay in the evidence table but cannot be plotted. Empty days mean no recorded observations, not proof of inactivity; the vertical scale is attempts per day for the selected workflow.

The source-attempts table sorts by start time, breaking ties by source row; invalid starts appear last. Status badges distinguish Succeeded (green), Failed (red), Stopped (amber), Aborted (purple) and unrecognized statuses (gray). **Exec time** is `(end − start)` in minutes; **Gap time** is `(current start − immediately previous attempt’s end)` in minutes, not start-to-start cadence. Both display at most two units: seconds below a minute (45s), minutes/seconds below an hour (34m 20s), hours/minutes below a day (23h 22m), and days/hours for longer durations (1d 6h). Round to the nearest smallest displayed unit, carrying overflow into the next unit: 1d 5h 50m 59s becomes 1d 6h; 23h 59m 40s becomes 1d 0h. Decimal minutes are converted mathematically from the original duration, not read as minute/second digits. Negative gaps retain a leading minus sign. A negative gap means **Overlaps = Yes**; zero or a positive gap means **No**. The first valid-start attempt shows N/A for gap/overlap. Missing, invalid or reversed timestamps make dependent values Unknown, never an assumed zero or No. A missing current end still permits gap/overlap calculation when the current start and previous interval are valid. Comparisons include every source attempt, including retries and duplicates, and are limited to the immediately previous start-ordered attempt of the same flow. These display calculations do not change migration decisions or the raw evidence supplied to the agent.

`python3 pipeline.py serve` serves the dashboard on `http://127.0.0.1:8765` and enables the correction form. Require reviewer, cadence, outcome and reason. Append each correction to `_data/overrides.json`; preserve automated evidence, update effective step 2 results and regenerate the dashboard. The latest active correction wins and survives subsequent clean runs. The **Corrections & history** section shows the full history. **Remove correction** requires a reviewer name, retains the record with `removed_at` and `removed_by`, and restores the previous active correction or automated result. If automation is incomplete, removing the last active correction restores UNKNOWN rather than approving the flow. Each history record has a stable `id`; older records receive a deterministic legacy ID. Any saved correction adds a **User override** badge beside the final outcome in the results table and workflow details, even when only cadence or reasoning changes and the outcome stays the same. This is a local prototype with a self-identified reviewer, not an authenticated approval system. In file-only mode the form explains how to start the server.

Other generated files in `dist/`: `evidence.json`, `data_issues.json`, `feedback.md`, `agent_prompt.txt`, `agent_schema.json`, `agent_response.json` when returned, `results.json`, and `manifest.json`. The manifest records run ID, input hashes, versions, timestamps, duration, completion/error, counts and reported agent token usage. The CLI uses its configured model; no exact backend model identifier is invented when the CLI does not report one. Full prompts and public agent responses are retained in append-only pipeline logs outside `dist/`; hidden reasoning events are excluded.

## Good and bad flows / acceptance examples

| Workflow | Good flow / output | Bad flow / output |
| --- | --- | --- |
| `wf_SLS_ORDERS_INCR` | Daily starts with supported failure retries → MIGRATE; explain why the retries are not extra schedule occurrences. | ≈49-minute minimum gap → TO ENGINEER. |
| `wf_INV_STOCK_HOURLY` | Daily starts and a retry crossing midnight → MIGRATE; identify the misleading name. | Copy “hourly” from the name. |
| `wf_WEB_CLICKS` | 72 hourly-aligned starts with jitter → MIGRATE; explain agreement with Python. | Reject a ≈52-minute gap or missing end time. |
| `wf_FIN_MONTH_END_CLOSE` | Three consecutive month ends → monthly, MIGRATE. | Automatically reject fewer than four runs. |
| `wf_BILL_INVOICE_WEEKLY` | Python identifies July 1, August 3, September 1 as first Monday–Friday days → monthly, MIGRATE; agent verifies the evidence and explains agreement. | Assume weekly from the name or leave no explanation after changing the decision. |
| `wf_PAY_AUTH_HOURLY` / `wf_TRD_POSITIONS` | Repeated 30-/15-minute windows → TO ENGINEER despite short history. | Average overnight gaps into cadence or wait for 90 days. |
| `wf_FIN_BUDGET_ACTUALS` | July 3, August 5 and September 3 are the third Monday–Friday day of each month → Python monthly, MIGRATE; agent verifies agreement. | Treat third weekday as third Monday, count weekends, or assume holiday exclusions. |
| `wf_MKT_SEGMENT_REBUILD` / `wf_RISK_EXPOSURE_WKLY` | Thirteen intact weekly starts plus one successful recovery 11h 39m / 13h 21m after failure → Python weekly, MIGRATE, with delayed-recovery evidence. | Increase the global retry limit, discard repeated secondary runs, or accept a recovery without surrounding scheduled starts. |
| `wf_FIN_QTR_REG_RPT` | One start → Python UNKNOWN; agent TO ENGINEER with a request for schedule configuration. | Name proves quarterly → MIGRATE. |
| `wf_MKT_CAMPAIGNS` | Flag unexplained inactivity; seek current schedule/retirement confirmation. Only explicit retirement correction → DO NOT MIGRATE. | Silence alone confirms retirement. |

Done when a clean run produces both CSVs and the dashboard; all workflows are accounted for; step 2 explains agreement and change; evidence references validate; incomplete reviews cannot masquerade as approvals; corrections survive rebuilds; and automated plus browser checks cover the examples, exports, filters and failure paths.
