import csv
import unittest
from pathlib import Path
from workflow_triage.presentation import attempt_timings, dashboard_evidence, file_activity_window

ROOT = Path(__file__).resolve().parents[1]


class AttemptTimingTests(unittest.TestCase):
    def test_shared_calendar_covers_whole_file_and_excludes_invalid_starts(self):
        evidence = {
            'long': {'attempts': [{'row': 2, 'start_time': '2026-06-29 01:00:00', 'end_time': ''},
                                  {'row': 3, 'start_time': '2026-09-26 23:50:33', 'end_time': ''}]},
            'short': {'attempts': [{'row': 4, 'start_time': '2026-09-24 07:00:00', 'end_time': ''},
                                   {'row': 5, 'start_time': 'invalid', 'end_time': ''}]},
        }
        window = file_activity_window(evidence)
        self.assertEqual((window['start'], window['end'], window['days']), ('2026-06-29', '2026-09-26', 90))
        rendered = dashboard_evidence(evidence)
        self.assertEqual(rendered['short']['attempts'][0]['plot_date'], '2026-09-24')
        self.assertIsNone(rendered['short']['attempts'][1]['plot_date'])
        self.assertIsNone(file_activity_window({'invalid': {'attempts': [evidence['short']['attempts'][1]]}}))
        self.assertIsNone(file_activity_window({}))

    def test_source_overlap_and_missing_end_regressions(self):
        with (ROOT/'_data/run_history.csv').open(newline='') as source:
            raw = [{'row':number, **row} for number,row in enumerate(csv.DictReader(source),2)]
        customer = {a['row']:a for a in attempt_timings([r for r in raw if r['workflow_name']=='wf_DIM_CUSTOMER'])}
        self.assertAlmostEqual(customer[249]['exec_minutes'],1790.9833333333333)
        self.assertEqual(customer[261]['overlaps_previous'],'Yes')
        self.assertEqual(customer[261]['previous_row'],249)
        self.assertAlmostEqual(customer[261]['gap_minutes'],-350.85)
        crm = {a['row']:a for a in attempt_timings([r for r in raw if r['workflow_name']=='wf_CRM_CONTACTS'])}
        self.assertIsNone(crm[439]['exec_minutes'])
        self.assertEqual(crm[439]['overlaps_previous'],'No')
        self.assertIsNone(crm[508]['gap_minutes'])
        self.assertEqual(crm[508]['overlaps_previous'],'Unknown')

    def test_order_midnight_touching_intervals_and_invalid_times(self):
        source = [
            {'row':4,'start_time':'2026-07-02 00:30:00','end_time':'2026-07-02 00:45:00'},
            {'row':2,'start_time':'2026-07-01 23:30:00','end_time':'2026-07-02 00:30:00'},
            {'row':3,'start_time':'2026-07-02 00:00:00','end_time':'2026-07-02 00:30:00'},
            {'row':5,'start_time':'2026-07-02 01:00:00','end_time':'2026-07-02 00:00:00'},
            {'row':6,'start_time':'2026-07-02 02:00:00','end_time':''},
            {'row':7,'start_time':'invalid','end_time':'2026-07-02 03:00:00'},
        ]
        result = attempt_timings(source)
        self.assertEqual([a['row'] for a in result],[2,3,4,5,6,7])
        self.assertEqual(result[0]['exec_minutes'],60)
        self.assertEqual(result[0]['overlaps_previous'],'N/A')
        self.assertEqual(result[1]['gap_minutes'],-30)
        self.assertEqual(result[1]['overlaps_previous'],'Yes')
        self.assertEqual(result[2]['gap_minutes'],0)
        self.assertEqual(result[2]['overlaps_previous'],'No')
        self.assertIsNone(result[3]['exec_minutes'])
        self.assertEqual(result[4]['overlaps_previous'],'Unknown')
        self.assertEqual(result[5]['overlaps_previous'],'Unknown')
        self.assertNotIn('exec_minutes',source[0])


if __name__=='__main__':unittest.main()
