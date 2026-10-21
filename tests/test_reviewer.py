"""Test the external process boundary without starting Codex or a model."""
import json
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from workflow_triage.reviewer import call_agent


class ReviewerAdapterTests(unittest.TestCase):
    def test_structured_answer_usage_and_public_audit(self):
        payload = {'reviews': []}
        events = [
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Public review summary'}},
            {'type': 'item.completed', 'item': {'type': 'reasoning', 'text': 'PRIVATE_TEST_EVENT'}},
            {'type': 'turn.completed', 'usage': {'input_tokens': 12, 'output_tokens': 3}},
        ]
        process = Mock(returncode=0)
        process.communicate.return_value = ('\n'.join(map(json.dumps, events)), '')

        def start(command, **kwargs):
            Path(command[command.index('--output-last-message')+1]).write_text(json.dumps(payload))
            self.assertEqual(command[command.index('--sandbox')+1], 'read-only')
            self.assertTrue(kwargs['start_new_session'])
            return process

        with tempfile.TemporaryDirectory() as folder:
            logfile = Path(folder)/'review.md'
            with patch('workflow_triage.reviewer.shutil.which', return_value='/test/codex'), \
                 patch('workflow_triage.reviewer.subprocess.Popen', side_effect=start):
                answer, usage = call_agent('Test prompt', logfile, 30)
            self.assertEqual(answer, payload)
            self.assertEqual(usage['input_tokens'], 12)
            process.communicate.assert_called_once_with('Test prompt', timeout=30)
            audit = logfile.read_text()
            self.assertIn('Test prompt', audit)
            self.assertIn('Public review summary', audit)
            self.assertNotIn('PRIVATE_TEST_EVENT', audit)

    def test_timeout_terminates_process_group_and_escalates_if_needed(self):
        process = Mock(pid=12345)
        process.communicate.side_effect = [subprocess.TimeoutExpired('codex', 1),
                                           subprocess.TimeoutExpired('codex', 5), ('', '')]
        with tempfile.TemporaryDirectory() as folder:
            with patch('workflow_triage.reviewer.shutil.which', return_value='/test/codex'), \
                 patch('workflow_triage.reviewer.subprocess.Popen', return_value=process), \
                 patch('workflow_triage.reviewer.os.killpg') as kill:
                with self.assertRaisesRegex(RuntimeError, 'timed out'):
                    call_agent('Test prompt', Path(folder)/'review.md', 1)
            self.assertEqual([call.args for call in kill.call_args_list],
                             [(12345, signal.SIGTERM), (12345, signal.SIGKILL)])

    def test_missing_binary_is_a_clear_failure(self):
        with patch('workflow_triage.reviewer.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'not installed'):
                call_agent('Test prompt', Path('/unused/test-log.md'))


if __name__ == '__main__':
    unittest.main()
