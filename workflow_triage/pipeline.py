"""Coordinate analysis, review and publication through explicit dependencies.

Legacy helper imports/wrappers remain available for existing callers. New code
should import contracts, serialization and corrections from their own modules.
"""
import json
import time
import uuid

from .analysis import RULE_VERSION, analyze
from .audit import log, now, redact
from .corrections import save_override as _save_override
from .repository import DEFAULT_ROOT, ArtifactRepository
from .review import (OUTCOMES, PROMPT_VERSION, apply_overrides, build_review_prompt, incomplete_results,
                     review_schema, reviewed_results, validate_review)
from .reviewer import Reviewer, call_agent
from .serialization import digest, write_csv, write_json

ROOT = DEFAULT_ROOT
DIST = ROOT / 'dist'


def render(results, evidence, manifest, *, repository=None):
    repository = repository if repository is not None else ArtifactRepository(ROOT)
    repository.render(results, evidence, manifest)


def publish(results, evidence, manifest, *, repository=None):
    repository = repository if repository is not None else ArtifactRepository(ROOT)
    repository.publish(results, evidence, manifest)


def save_override(flow_id, outcome, cadence, reason, reviewer, *, repository=None):
    repository = repository if repository is not None else ArtifactRepository(ROOT)
    return _save_override(flow_id, outcome, cadence, reason, reviewer, repository=repository)


def run_pipeline(skip_agent=False, timeout=600, *, repository=None, reviewer: Reviewer = None):
    repository = repository if repository is not None else ArtifactRepository(ROOT)
    reviewer = reviewer if reviewer is not None else call_agent
    root, dist = repository.root, repository.dist
    started = time.monotonic()
    run_id = str(uuid.uuid4())
    logfile = root / 'logs' / ('%s-pipeline-%s.md' % (now()[:10], run_id))
    log(logfile, 'pipeline', 'run started',
        'Run %s; skip_agent=%s; timeout=%ss' % (run_id, skip_agent, timeout))
    with repository.locked():
        repository.reset_outputs()
        manifest = {
            'run_id': run_id, 'started_at': now(), 'state': 'running',
            'rule_version': RULE_VERSION, 'prompt_version': PROMPT_VERSION,
            'agent': 'Codex CLI configured default',
            'timezone': 'source timestamps unspecified; run timestamps UTC',
            'log_file': str(logfile.relative_to(root)),
        }
        try:
            source, feedback_path = root/'_data/run_history.csv', root/'_data/feedback.md'
            prompt_path = root/'prompts/review.txt'
            manifest['input_sha256'] = {
                str(path.relative_to(root)): digest(path)
                for path in (source, feedback_path, prompt_path)
            }
            step1, evidence, issues = analyze(source, run_id)
            if not step1:
                raise ValueError('Input CSV has no workflows')
            manifest['workflow_count'] = len(step1)
            manifest['source_row_count'] = sum(row['total_rows'] for row in step1)
            write_csv(dist/'step1_results.csv', step1)
            write_json(dist/'evidence.json', evidence)
            write_json(dist/'data_issues.json', issues)
            feedback = feedback_path.read_text()
            (dist/'feedback.md').write_text(feedback, encoding='utf-8')
            prompt = build_review_prompt(prompt_path.read_text(),
                                         (dist/'step1_results.csv').read_text(), feedback, evidence)
            (dist/'agent_prompt.txt').write_text(prompt, encoding='utf-8')
            write_json(dist/'agent_schema.json', review_schema())
            overrides = repository.load_overrides()
            if repository.overrides_path.exists():
                manifest['input_sha256']['_data/overrides.json'] = digest(repository.overrides_path)

            # Publish pending rows before invoking external code: stale approvals
            # cannot survive an interrupted or unsuccessful review.
            pending = incomplete_results(step1, 'Waiting for the second-stage agent.')
            repository.publish(apply_overrides(pending, overrides), evidence, manifest)
            print('Step 1: %s workflows written. %s' % (
                len(step1), 'Agent skipped.' if skip_agent else 'Running agent review…'), flush=True)
            reviews = {}
            problem = 'Agent review was intentionally skipped.' if skip_agent else ''
            if not skip_agent:
                try:
                    payload, usage = reviewer(prompt, logfile, timeout)
                    write_json(dist/'agent_response.json', payload)
                    reviews = validate_review(payload, step1)
                    manifest['agent_usage'] = usage
                except (RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
                    problem = str(exc)
                    log(logfile, 'pipeline', 'agent failure', problem)
            results = reviewed_results(step1, reviews) if reviews else incomplete_results(step1, problem)
            results = apply_overrides(results, overrides)
            manifest.update(state='complete' if reviews else 'incomplete', finished_at=now(),
                            duration_seconds=round(time.monotonic()-started, 2), error=problem)
            repository.publish(results, evidence, manifest)
            log(logfile, 'pipeline', 'run outcome', json.dumps(manifest, indent=2))
            print('Dashboard: %s\nReview: %s; outcomes: %s' % (
                dist/'index.html', manifest['state'], manifest['outcomes']), flush=True)
            return 0 if reviews or skip_agent else 1
        except Exception as exc:
            manifest.update(state='failed', finished_at=now(), error=redact(str(exc)))
            write_json(dist/'manifest.json', manifest)
            repository.render([], {}, manifest)
            log(logfile, 'pipeline', 'run failure', str(exc))
            raise
