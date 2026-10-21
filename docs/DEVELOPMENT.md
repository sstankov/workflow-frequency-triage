# Development guide

Start with the [README](../README.md), [specification](../SPEC.md) and [repository instructions](../AGENTS.md). The [pipeline contract](PIPELINE.md) defines inference policy, output fields and review behavior.

## Responsibilities and dependencies

The root `pipeline.py` is the CLI entry point. Implementation modules live in `workflow_triage/`:

| Module | Responsibility |
| --- | --- |
| `analysis.py`, `cadence.py` | Source accounting, cadence candidates, provisional eligibility and explanations. |
| `review.py` | Review schema, validation, decision assembly and override policy; no filesystem/model calls. |
| `reviewer.py` | Callable `Reviewer` protocol and Codex process adapter, including timeout cleanup. |
| `pipeline.py` | Coordinate analysis, review and publication using explicit dependencies. |
| `repository.py`, `serialization.py` | Paths, locking, disposable artifacts and safe CSV/JSON encoding. |
| `corrections.py` | Persist human corrections/removal audit and republish effective decisions. |
| `presentation.py` | Prepare dashboard evidence and render HTML from explicit inputs. |
| `server.py` | Loopback HTTP transport, delegating corrections to their service. |
| `audit.py` | Append-only public logs and credential redaction. |

`run_pipeline(repository=..., reviewer=...)` accepts an `ArtifactRepository` and a callable reviewer returning `(structured_payload, usage)`. `make_server(port, repository=...)` accepts the same repository boundary. Tests inject temporary repositories and test reviewers instead of patching global paths or calling a model. Compatibility helpers in `workflow_triage.pipeline` remain for existing callers; new code should import from the module that owns the behavior.

Keep cadence and review policy as ordinary functions. Introduce adapters at actual external boundaries; avoid a class hierarchy for each schedule rule. Add schedule families and rejection cases instead of workflow-name exceptions.

## Verification and maintenance

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

The suite covers inference, delayed recovery safeguards, evidence validation, missing/invalid reviews, subprocess timeout handling, artifact isolation, corrections, HTML escaping and CSV export. Tests do not consume model usage or overwrite the live dashboard. For behavior changes, add a regression that distinguishes the accepted case from plausible false positives.

Edit `web/dashboard.html` for presentation changes and `prompts/review.txt` for agent instructions. Generated `dist/` is disposable. A full `python3 pipeline.py run` invokes a real reviewer and refreshes the feedback snapshot; `--skip-agent` deliberately publishes incomplete results. Never silently substitute a saved response for a fresh production review.

Keep the short specification and detailed contract aligned when behavior changes. Update `RULE_VERSION` or `PROMPT_VERSION` when the corresponding inference/review policy changes; a documentation-only correction does not require a new version or model run. Preserve source assignment/feedback and append-only logs as evidence. Before sharing a submission, include `_data/` and check that both CSVs, the dashboard and manifest belong to the intended completed run.
