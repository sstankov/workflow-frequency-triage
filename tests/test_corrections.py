"""Corrections can be removed without erasing history or reviving removed records."""
import copy
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from workflow_triage.corrections import remove_override, save_override
from workflow_triage.repository import ArtifactRepository
from workflow_triage.review import apply_overrides, correction_id
from workflow_triage.serialization import write_json
from workflow_triage.server import make_server


class CorrectionRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ('dist', '_data', 'web'):
            (self.root / folder).mkdir()
        (self.root / 'web/dashboard.html').write_text('<script>__PIPELINE_DATA__</script>')
        self.repository = ArtifactRepository(self.root)
        self.base = [dict(flow_id='wf_A', agent_outcome='MIGRATE', step1_outcome='MIGRATE',
                          final_cadence='daily', outcome_explanation='Daily scheduled starts.',
                          review_complete=True)]
        write_json(self.root / 'dist/results.json', apply_overrides(copy.deepcopy(self.base), {}))
        write_json(self.root / 'dist/evidence.json', {})
        write_json(self.root / 'dist/manifest.json', {'input_sha256': {}})

    def save(self, outcome='TO ENGINEER', cadence='needs confirmation'):
        save_override('wf_A', outcome, cadence, 'Evidence supports this correction.',
                      'Original reviewer', repository=self.repository)
        return self.result()['override_history'][-1]['id']

    def result(self):
        return self.repository.read_output('results.json')[0]

    def remove(self, identity):
        remove_override('wf_A', identity, 'Removing reviewer', repository=self.repository)

    def test_last_removal_restores_all_automated_fields_and_retains_audit(self):
        identity = self.save()
        self.remove(identity)
        row = self.result()
        self.assertEqual((row['final_outcome'], row['effective_cadence'], row['effective_explanation']),
                         ('MIGRATE', 'daily', 'Daily scheduled starts.'))
        self.assertEqual(row['decision_source'], 'agent')
        self.assertFalse(row['outcome_changed'])
        removed = row['override_history'][0]
        self.assertEqual(removed['reviewer'], 'Original reviewer')
        self.assertEqual(removed['removed_by'], 'Removing reviewer')
        self.assertTrue(removed['removed_at'])
        self.assertIn('correction removed', next((self.root / 'logs').glob('*.md')).read_text())
        self.assertEqual(self.repository.read_output('manifest.json')['outcomes'], {'MIGRATE': 1})
        self.assertIn('MIGRATE', (self.root / 'dist/step2_results.csv').read_text())
        rebuilt = apply_overrides(copy.deepcopy(self.base), self.repository.load_overrides())[0]
        self.assertEqual(rebuilt, row)

    def test_latest_removal_restores_previous_and_skips_removed_records(self):
        first = self.save('TO ENGINEER', 'weekly')
        middle = self.save('UNKNOWN', 'unresolved')
        latest = self.save('DO NOT MIGRATE', 'retired')
        self.remove(middle)
        self.assertEqual(self.result()['final_outcome'], 'DO NOT MIGRATE')
        self.remove(latest)
        self.assertEqual(self.result()['effective_cadence'], 'weekly')
        self.assertEqual(self.result()['decision_source'], 'human override')
        self.remove(first)
        self.assertEqual(self.result()['decision_source'], 'agent')
        self.assertEqual(len(self.result()['override_history']), 3)

    def test_legacy_ids_remain_stable_through_removal(self):
        legacy = dict(timestamp='2026-10-21T10:00:00+00:00', outcome='TO ENGINEER',
                      cadence='weekly', reason='Review needed.', reviewer='Legacy reviewer')
        write_json(self.repository.overrides_path, {'wf_A': [legacy, dict(legacy)]})
        histories = apply_overrides(copy.deepcopy(self.base), self.repository.load_overrides())[0]['override_history']
        first, second = [item['id'] for item in histories]
        self.assertNotEqual(first, second)
        self.remove(first)
        self.assertEqual([item['id'] for item in self.result()['override_history']], [first, second])
        self.remove(second)
        self.assertEqual(self.result()['decision_source'], 'agent')

    def test_stale_or_foreign_removal_does_not_mutate_history(self):
        identity = self.save()
        self.remove(identity)
        before = self.repository.overrides_path.read_bytes()
        for flow, target, reviewer in [('wf_A', identity, 'Reviewer'), ('wf_A', 'missing', 'Reviewer'),
                                       ('other_flow', identity, 'Reviewer'), ('wf_A', identity, '  ')]:
            with self.subTest(flow=flow, target=target, reviewer=reviewer), self.assertRaises(ValueError):
                remove_override(flow, target, reviewer, repository=self.repository)
            self.assertEqual(self.repository.overrides_path.read_bytes(), before)

    def test_removal_does_not_approve_incomplete_review(self):
        self.base[0].update(agent_outcome='UNKNOWN', review_complete=False,
                            outcome_explanation='Review incomplete.', final_cadence='unknown')
        write_json(self.root / 'dist/results.json', apply_overrides(copy.deepcopy(self.base), {}))
        identity = self.save('MIGRATE', 'monthly')
        self.remove(identity)
        self.assertEqual(self.result()['final_outcome'], 'UNKNOWN')
        self.assertEqual(self.result()['decision_source'], 'incomplete review')

    def test_partial_removal_metadata_is_rejected(self):
        self.save()
        overrides = self.repository.load_overrides()
        overrides['wf_A'][0]['removed_at'] = '2026-10-21'
        with self.assertRaises(ValueError):
            apply_overrides(copy.deepcopy(self.base), overrides)

    def test_http_removal_checks_origin_and_updates_published_results(self):
        identity = self.save()
        httpd = make_server(0, repository=self.repository)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        origin = 'http://127.0.0.1:%s' % httpd.server_port
        def request(source, **changes):
            fields = dict(flow_id='wf_A', correction_id=identity, reviewer='API reviewer')
            fields.update(changes)
            return urllib.request.Request(origin+'/api/override/remove', data=json.dumps(fields).encode(),
                headers={'Content-Type':'application/json', 'Origin':source}, method='POST')
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request('https://untrusted.example'))
            self.assertEqual(error.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request(origin, unexpected='field'))
            self.assertEqual(error.exception.code, 400)
            self.assertEqual(self.result()['decision_source'], 'human override')
            with urllib.request.urlopen(request(origin)) as response:
                self.assertTrue(json.load(response)['ok'])
            with urllib.request.urlopen(origin+'/results.json') as response:
                self.assertEqual(json.load(response)[0]['decision_source'], 'agent')
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
