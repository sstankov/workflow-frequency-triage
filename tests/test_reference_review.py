"""Reference evidence must come from the reviewed snapshot and remain inert text."""
import json
import tempfile
import unittest
from pathlib import Path
from workflow_triage.presentation import feedback_sources
from workflow_triage.repository import ArtifactRepository


class ReferenceReviewTests(unittest.TestCase):
    def test_numbered_sources_preserve_quotes_and_exact_workflow_mentions(self):
        text = '# Feedback\n\n## 1. Operations, 22 Sep\n\n> wf_A_ARCHIVE is daily.\n> Second line.\n\n## 6. Support\n\n> Empty end times are valid.\n'
        sources = feedback_sources(text)
        self.assertEqual(set(sources), {'1', '6'})
        self.assertEqual(sources['1']['named_flows'], ['wf_A_ARCHIVE'])
        self.assertEqual(sources['1']['text'], 'wf_A_ARCHIVE is daily.\nSecond line.')
        self.assertEqual(sources['6']['named_flows'], [])

    def test_render_uses_snapshot_not_new_feedback_and_escapes_markup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);dist=root/'dist';dist.mkdir()
            (root/'web').mkdir();(root/'_data').mkdir()
            (root/'web/dashboard.html').write_text('<script>const data=__PIPELINE_DATA__;</script>')
            (root/'_data/feedback.md').write_text('## 1. Changed input\n> New statement.')
            (dist/'feedback.md').write_text('## 1. Reviewed input\n> </script><script>alert(1)</script>')
            repository=ArtifactRepository(root)
            repository.render([],{}, {})
            output=(dist/'index.html').read_text()
            self.assertNotIn('</script><script>',output)
            data=json.loads(output.removeprefix('<script>const data=').removesuffix(';</script>'))
            self.assertEqual(data['feedback_sources']['1']['title'],'Reviewed input')
            (dist/'feedback.md').unlink()
            repository.render([],{}, {})
            self.assertIn('"feedback_sources": {}',(dist/'index.html').read_text())

if __name__ == '__main__':
    unittest.main()
