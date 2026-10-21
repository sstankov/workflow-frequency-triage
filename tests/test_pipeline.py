import copy
import csv
import json
import io
import tempfile
import unittest
import threading
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import Mock
from workflow_triage.analysis import analyze
from workflow_triage import pipeline
from workflow_triage.repository import ArtifactRepository
from workflow_triage.review import validate_review
from workflow_triage.serialization import digest, write_csv

ROOT = Path(__file__).resolve().parents[1]

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.rows,_,_=analyze(ROOT/'_data/run_history.csv','test')
        self.payload={'reviews':[dict(flow_id=r['flow_id'],final_cadence='unknown',interval_minutes=None,agent_outcome='TO ENGINEER',outcome_explanation='The available evidence requires schedule configuration to resolve the recurring cadence.',comparison_explanation='The Python decision is reviewed against the raw records; unresolved frequency requires an engineer.',next_action='Ask the owner for schedule configuration.',evidence_rows=[r['evidence_rows'][0]],feedback_sections=[5]) for r in self.rows]}

    def test_missing_duplicate_crossflow_and_empty_explanations_rejected(self):
        self.assertEqual(len(validate_review(self.payload,self.rows)),40)
        for mutation in ('missing','duplicate','wrong_evidence','empty_reason','unconfirmed_retirement','unknown_final','fast_migrate'):
            value=copy.deepcopy(self.payload)
            first=value['reviews'][0]
            if mutation=='missing':value['reviews'].pop()
            if mutation=='duplicate':value['reviews'][-1]=first
            if mutation=='wrong_evidence':first['evidence_rows']=[999999]
            if mutation=='empty_reason':first['outcome_explanation']='unchanged'
            if mutation=='unconfirmed_retirement':first['agent_outcome']='DO NOT MIGRATE'
            if mutation=='unknown_final':first['agent_outcome']='UNKNOWN'
            if mutation=='fast_migrate':first.update(agent_outcome='MIGRATE',final_cadence='every 30 minutes',interval_minutes=30)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_review(value,self.rows)

    def project(self,folder):
        root=Path(folder)
        (root/'_data').mkdir();(root/'web').mkdir();(root/'prompts').mkdir()
        for source in ['_data/run_history.csv','_data/feedback.md','web/dashboard.html','prompts/review.txt']:
            (root/source).write_bytes((ROOT/source).read_bytes())
        return root

    def test_clean_rebuild_and_durable_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.project(folder)
            repository=ArtifactRepository(root)
            reviewer=Mock(return_value=(self.payload,{}))
            self.assertEqual(pipeline.run_pipeline(repository=repository, reviewer=reviewer),0)
            (root/'dist/stale.txt').write_text('old output')
            source_hash=digest(root/'_data/run_history.csv')
            pipeline.save_override(self.rows[0]['flow_id'],'DO NOT MIGRATE','retired','Owner confirms this workflow is retired.','Test reviewer',repository=repository)
            self.assertEqual(pipeline.run_pipeline(repository=repository, reviewer=reviewer),0)
            self.assertFalse((root/'dist/stale.txt').exists())
            self.assertEqual(digest(root/'_data/run_history.csv'),source_hash)
            final=json.loads((root/'dist/results.json').read_text())[0]
            self.assertEqual(final['final_outcome'],'DO NOT MIGRATE')
            self.assertEqual(final['agent_outcome'],'TO ENGINEER')
            self.assertEqual(final['decision_source'],'human override')
            self.assertEqual(len(list(csv.DictReader(io.StringIO((root/'dist/step2_results.csv').read_text())))),40)

    def test_agent_failure_replaces_old_approvals_with_incomplete_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.project(folder)
            repository=ArtifactRepository(root)
            reviewer=Mock(side_effect=RuntimeError('Test agent unavailable'))
            self.assertEqual(pipeline.run_pipeline(repository=repository, reviewer=reviewer),1)
            results=json.loads((root/'dist/results.json').read_text())
            self.assertTrue(all(r['final_outcome']=='UNKNOWN' and not r['review_complete'] for r in results))
            self.assertIn('Test agent unavailable',(root/'dist/index.html').read_text())

    def test_http_dashboard_to_persistent_correction(self):
        from workflow_triage import server
        with tempfile.TemporaryDirectory() as folder:
            root=self.project(folder)
            repository=ArtifactRepository(root)
            reviewer=Mock(return_value=(self.payload,{}))
            pipeline.run_pipeline(repository=repository, reviewer=reviewer)
            httpd=server.make_server(0,repository=repository)
            worker=threading.Thread(target=httpd.serve_forever,daemon=True);worker.start()
            origin='http://127.0.0.1:%s' % httpd.server_port
            try:
                with urllib.request.urlopen(origin) as response:
                    self.assertIn(b'Review migration eligibility.',response.read())
                body=json.dumps(dict(flow_id=self.rows[0]['flow_id'],outcome='MIGRATE',cadence='monthly',reason='Test correction: supplied schedule confirms monthly cadence.',reviewer='Integration test')).encode()
                request=urllib.request.Request(origin+'/api/override',data=body,headers={'Content-Type':'application/json','Origin':origin},method='POST')
                with urllib.request.urlopen(request) as response:
                    self.assertTrue(json.load(response)['ok'])
                history=json.loads((root/'_data/overrides.json').read_text())
                self.assertEqual(history[self.rows[0]['flow_id']][-1]['reviewer'],'Integration test')
                with urllib.request.urlopen(origin+'/step2_results.csv') as response:
                    first=list(csv.DictReader(io.StringIO(response.read().decode())))[0]
                    self.assertEqual(first['final_outcome'],'MIGRATE')
                    self.assertEqual(first['agent_outcome'],'TO ENGINEER')
                request=urllib.request.Request(origin+'/api/override',data=body,headers={'Content-Type':'application/json','Origin':'https://untrusted.example'},method='POST')
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(request)
                self.assertEqual(denied.exception.code,403)
            finally:
                httpd.shutdown();httpd.server_close();worker.join()

    def test_html_and_csv_escape_untrusted_text(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.project(folder);(root/'dist').mkdir()
            repository=ArtifactRepository(root)
            repository.render([{'flow_id':'</script><script>alert(1)</script>'}],{}, {})
            html=(root/'dist/index.html').read_text()
            self.assertNotIn('</script><script>alert(1)</script>',html)
            write_csv(root/'dist/test.csv',[{'flow_id':'=1+1','explanation':'a,b\nsecond line'}])
            record=list(csv.DictReader(io.StringIO((root/'dist/test.csv').read_text())))[0]
            self.assertEqual(record['flow_id'],"'=1+1")
            self.assertEqual(record['explanation'],'a,b\nsecond line')

if __name__=='__main__':unittest.main()
