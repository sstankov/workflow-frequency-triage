"""Filesystem boundary for one project and its disposable output artifacts."""
import fcntl
import json
import shutil
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from .presentation import render_dashboard
from .review import OUTCOMES
from .serialization import write_csv, write_json

DEFAULT_ROOT = Path(__file__).resolve().parents[1]


class ArtifactRepository:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root).resolve()
        self.dist = self.root / 'dist'
        self.overrides_path = self.root / '_data' / 'overrides.json'

    @contextmanager
    def locked(self):
        """Serialize rebuilds and corrections within this project only."""
        with (self.root / '.pipeline.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def reset_outputs(self):
        if self.dist.is_symlink():
            raise ValueError('Refusing to clean a symlinked dist directory')
        if self.dist.exists():
            shutil.rmtree(self.dist)
        self.dist.mkdir()

    def load_overrides(self):
        return json.loads(self.overrides_path.read_text()) if self.overrides_path.exists() else {}

    def read_output(self, filename):
        return json.loads((self.dist / filename).read_text())

    def render(self, results, evidence, manifest):
        snapshot = self.dist / 'feedback.md'
        html = render_dashboard(
            (self.root / 'web' / 'dashboard.html').read_text(),
            results, evidence, manifest,
            snapshot.read_text() if snapshot.exists() else '',
            OUTCOMES,
        )
        (self.dist / 'index.html').write_text(html, encoding='utf-8')

    def publish(self, results, evidence, manifest):
        write_csv(self.dist / 'step2_results.csv', results)
        write_json(self.dist / 'results.json', results)
        manifest['outcomes'] = dict(Counter(row['final_outcome'] for row in results))
        manifest['changed_count'] = sum(row['outcome_changed'] for row in results)
        write_json(self.dist / 'manifest.json', manifest)
        self.render(results, evidence, manifest)
