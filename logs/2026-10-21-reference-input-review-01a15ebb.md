
## 2026-10-21T16:57:34.647403+03:00 — user — prompt

Lets add in details of the flow → if there was reference input used. City what and how that reflect for us - as structured review in details.

## 2026-10-21T16:57:34.647550+03:00 — side-assistant — progress update

I’ll add a structured “Reference input used” section to flow details, showing the cited feedback, how it relates to the flow, and whether the review confirmed or changed the outcome. I’ll make clear that a citation alone does not prove the feedback caused the decision.

## 2026-10-21T16:57:34.647553+03:00 — side-assistant — tool actions

Inspected dashboard and rendering entry points read-only. Existing flow navigation changes are present and will be preserved. This side task is scoped to reference evidence presentation; no cadence or decision rule changes.

## 2026-10-21T17:00:36.137387+03:00 — side-assistant — progress update

The section now shows which feedback was cited, whether it names the workflow, and the reviewer’s explanation of the outcome. I’m checking that it displays the feedback snapshot used for that run, so later edits cannot silently change the evidence shown.

## 2026-10-21T17:00:36.137539+03:00 — side-assistant — tool actions and verification

Added numbered feedback parsing and embedded the existing run snapshot during HTML rendering. Added structured Reference input used section with citation count, automated outcome comparison, reviewer explanation, evidence assessment, source headings, exact text disclosures, direct-name/general-guidance distinction, pending/no-citation/missing-text states and human override clarification. Preserved existing navigation and decision outputs; did not invoke another agent review. Updated SPEC.md. Two focused tests passed for exact source mentions, snapshot provenance, unavailable snapshot and markup escaping; JavaScript syntax check passed. Browser verified direct citation with confirmed MIGRATE for wf_SLS_ORDERS_INCR and general guidance with UNKNOWN → TO ENGINEER for wf_DQ_ADHOC_RECON. Saved dist/reference-input-preview.png. An initial no-op patch target mismatch made no changes. Browser preview binding and a close-button accessible-name lookup failed; recovered using the created preview tab and existing close control ID.

## 2026-10-21T17:00:47.761987+03:00 — side-assistant — verification

Full test suite passed: 36 tests.

## 2026-10-21T17:00:47.762135+03:00 — side-assistant — final response

Added **Reference input used** to flow details, showing:

- Cited feedback source and original text.
- Whether it names the workflow or provides general guidance.
- The reviewer’s explanation and evidence assessment.
- Whether the automated outcome changed or stayed the same.

It distinguishes citations from proven causal impact. **All 36 tests pass.**

![Structured reference review](/Users/sstankov/git/workflow-frequency-triage/dist/reference-input-preview.png)
