"""Durable human correction use case, separate from pipeline execution."""
import json
from uuid import uuid4

from .audit import log, now
from .repository import ArtifactRepository
from .review import OUTCOMES, apply_overrides, correction_id
from .serialization import digest, write_json


def save_override(flow_id, outcome, cadence, reason, reviewer, *, repository=None):
    repository = repository if repository is not None else ArtifactRepository()
    if outcome not in OUTCOMES or not all(isinstance(s, str) and s.strip() for s in (flow_id, cadence, reason, reviewer)):
        raise ValueError('Flow, outcome, cadence, reason and reviewer are required')
    with repository.locked():
        results = repository.read_output('results.json')
        if flow_id not in {row['flow_id'] for row in results}:
            raise ValueError('Unknown workflow')
        overrides = repository.load_overrides()
        change = {'id': str(uuid4()), 'timestamp': now(), 'outcome': outcome, 'cadence': cadence.strip(),
                  'reason': reason.strip(), 'reviewer': reviewer.strip()}
        overrides.setdefault(flow_id, []).append(change)
        publish_overrides(repository, results, overrides)
        log(repository.root / 'logs' / (now()[:10]+'-corrections.md'), reviewer,
            'workflow correction', json.dumps({'flow_id': flow_id, **change}, indent=2))


def publish_overrides(repository, results, overrides):
    updated = apply_overrides(results, overrides)
    write_json(repository.overrides_path, overrides)
    manifest = repository.read_output('manifest.json')
    manifest['overrides_updated_at'] = now()
    manifest['input_sha256']['_data/overrides.json'] = digest(repository.overrides_path)
    repository.publish(updated, repository.read_output('evidence.json'), manifest)


def remove_override(flow_id, correction_id_to_remove, reviewer, *, repository=None):
    """Retire one correction while retaining its contents and removal audit."""
    repository = repository if repository is not None else ArtifactRepository()
    if not all(isinstance(value, str) and value.strip()
               for value in (flow_id, correction_id_to_remove, reviewer)):
        raise ValueError('Workflow, correction and your name are required')
    with repository.locked():
        results = repository.read_output('results.json')
        if flow_id not in {row['flow_id'] for row in results}:
            raise ValueError('Unknown workflow')
        overrides = repository.load_overrides()
        history = overrides.get(flow_id, [])
        change = next((item for index, item in enumerate(history)
                       if correction_id(flow_id, index, item) == correction_id_to_remove), None)
        if change is None:
            raise ValueError('Correction not found for this workflow. Refresh and try again.')
        if change.get('removed_at'):
            raise ValueError('This correction has already been removed. Refresh to see the current decision.')
        change.update(id=correction_id_to_remove, removed_at=now(), removed_by=reviewer.strip())
        publish_overrides(repository, results, overrides)
        log(repository.root / 'logs' / (now()[:10]+'-corrections.md'), reviewer.strip(),
            'correction removed', json.dumps({'flow_id': flow_id, **change}, indent=2))
