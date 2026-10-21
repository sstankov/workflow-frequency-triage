"""Behavioral coverage across cadence families, independent of workflow names."""
import unittest
from datetime import datetime, timedelta
from workflow_triage.cadence import infer, unresolved_reason, delayed_weekly_recovery


def runs(starts, statuses=None):
    return [dict(time=datetime.fromisoformat(s) if isinstance(s,str) else s,
                 status=statuses[i] if statuses else 'Succeeded', row=i+2)
            for i,s in enumerate(starts)]


class CadenceFamilyTests(unittest.TestCase):
    def test_general_intervals_not_only_a_fixed_allowlist(self):
        for minutes in (1,7,20,45,55,59,59.5,60,90,120,420,720,2880,4320,30240):
            count= max(6, int(3*1440/minutes)+1) if minutes>=60 else int(2*1440/minutes)+1
            # Short fast schedules tested in daily windows to keep tests small.
            starts=([datetime(2026,1,d,8)+timedelta(minutes=minutes*i) for d in (1,2,3) for i in range(6)]
                    if minutes<60 else [datetime(2026,1,1)+timedelta(minutes=minutes*i) for i in range(count)])
            with self.subTest(minutes=minutes):
                model=infer(runs(starts))
                self.assertIsNotNone(model)
                self.assertEqual(model['interval'],minutes)

    def test_uneven_daily_times_and_fastest_pair(self):
        for clocks,fastest in [([(6,0),(10,0),(19,0)],240), ([(6,0),(6,30),(19,0)],30)]:
            starts=[datetime(2026,1,d,h,m) for d in (1,2,3,4) for h,m in clocks]
            model=infer(runs(starts))
            self.assertEqual(model['family'],'daily clock')
            self.assertEqual(model['interval'],fastest)
            self.assertEqual(len(model['retries']),0)

    def test_weekly_day_and_time_sets(self):
        starts=[datetime(2026,1,5)+timedelta(weeks=w,days=d,hours=h) for w in range(4) for d,h in [(0,6),(2,10),(4,18)]]
        model=infer(runs(starts))
        self.assertEqual(model['family'],'weekly clock')
        self.assertIn('Mon 06:00',model['cadence'])
        self.assertIn('Fri 18:00',model['cadence'])

    def test_calendar_cycle_families(self):
        cases=[(['2026-01-15','2026-03-15','2026-05-15'],'every two months'),
               (['2025-10-31','2026-01-31','2026-04-30'],'quarterly'),
               (['2025-01-31','2025-07-31','2026-01-31'],'every six months'),
               (['2024-02-29','2025-02-28','2026-02-28'],'annually')]
        for dates,prefix in cases:
            with self.subTest(prefix=prefix):
                model=infer(runs([d+' 06:00' for d in dates]))
                self.assertEqual(model['family'],'calendar')
                self.assertTrue(model['cadence'].startswith(prefix))
                self.assertIsNone(model['interval'])

    def test_calendar_date_rule_families(self):
        cases=[(['2026-07-24','2026-08-25','2026-09-25'],'day 25 moved to previous'),
               (['2026-07-27','2026-08-25','2026-09-25'],'day 25 moved to next'),
               (['2026-07-29','2026-08-27','2026-09-28'],'third Monday–Friday day from month end'),
               (['2026-07-29','2026-08-29','2026-09-28'],'2 days before month end'),
               (['2026-07-12','2026-08-09','2026-09-13'],'weekday Sunday occurrence 2'),
               (['2026-07-26','2026-08-30','2026-09-27'],'last Sunday')]
        for dates,label in cases:
            with self.subTest(label=label):
                model=infer(runs([d+' 06:00' for d in dates]))
                self.assertIsNotNone(model)
                self.assertTrue(any(label in p for p in model['matching_patterns']),model['matching_patterns'])

    def test_arbitrary_repeated_month_days(self):
        starts=[datetime(2026,m,d,6) for m in (7,8,9) for d in (5,20)]
        model=infer(runs(starts))
        self.assertEqual(model['cadence'],'twice monthly, days 5 and 20')
        starts=[datetime(2026,m,d,6) for m in (7,8,9) for d in (3,12,24)]
        self.assertEqual(infer(runs(starts))['cadence'],'monthly, days 3 and 12 and 24')

    def test_missing_cycles_do_not_claim_calendar_and_short_evidence_explains_why(self):
        self.assertIsNone(infer(runs(['2026-07-03 06:00','2026-09-03 06:00','2026-10-05 06:00'])))
        self.assertIsNone(infer(runs(['2026-07-03 06:00'])))
        self.assertIn('1 valid unique start',unresolved_reason(runs(['2026-07-03 06:00'])))

    def test_change_and_irregular_extra_run_are_not_approved(self):
        starts=[datetime(2026,1,d,6 if d<5 else 11) for d in range(1,9)]
        self.assertIsNone(infer(runs(starts)))
        starts=[datetime(2026,1,d,6) for d in range(1,9)]+[datetime(2026,1,3,12,37)]
        self.assertIsNone(infer(runs(sorted(starts))))

    def test_no_successful_runs_are_hidden_as_retries(self):
        starts=[datetime(2026,1,d,h,m) for d in (1,2,3) for h,m in [(6,0),(6,30),(19,0)]]
        statuses=['Failed' if i%3==0 else 'Succeeded' for i in range(len(starts))]
        model=infer(runs(starts,statuses))
        self.assertEqual(model['interval'],30)
        self.assertFalse(model['retries'])

    def test_hourly_jitter_does_not_create_subhourly_cadence(self):
        starts=[datetime(2026,1,1)+timedelta(hours=i,minutes=[0,8,0,-3][i%4]) for i in range(72)]
        model=infer(runs(starts))
        self.assertEqual(model['interval'],60)

class DelayedRecoveryTests(unittest.TestCase):
    def weekly(self, failure=3, delay=13, status='Failed', recovery_status='Succeeded', count=8):
        base=runs([datetime(2026,1,2,20)+timedelta(weeks=i) for i in range(count)])
        base[failure]['status']=status
        extra=dict(time=base[failure]['time']+timedelta(hours=delay),status=recovery_status,row=100)
        return sorted(base+[extra],key=lambda r:r['time'])

    def test_isolated_recovery_has_auditable_surrounding_evidence(self):
        for status in ('Failed','Aborted','Stopped'):
            with self.subTest(status=status):
                source=self.weekly(status=status)
                model=infer(source)
                self.assertEqual(model['cadence'],'weekly')
                self.assertEqual(len(model['runs']),8)
                self.assertEqual([r['row'] for r in model['retries']],[100])
                evidence=model['delayed_recoveries'][0]
                self.assertEqual(evidence,dict(row=100,failed_row=5,delay_minutes=780.0,
                                               preceding_scheduled_rows=[3,4],following_scheduled_rows=[6,7]))
                self.assertEqual(len(source),9)

    def test_window_boundaries_preserve_normal_retry_rule(self):
        for hours,accepted in [(6,False),(6+1/60,True),(24,True),(24+1/60,False)]:
            with self.subTest(hours=hours):
                self.assertEqual(delayed_weekly_recovery(self.weekly(delay=hours)) is not None,accepted)
        self.assertEqual(infer(self.weekly(delay=6))['cadence'],'weekly')
        self.assertIsNone(infer(self.weekly(delay=25)))

    def test_successful_predecessor_and_failed_recovery_are_not_grouped(self):
        self.assertIsNone(infer(self.weekly(status='Succeeded')))
        self.assertIsNone(infer(self.weekly(recovery_status='Failed')))

    def test_requires_two_occurrences_on_each_side_and_six_total(self):
        for failure,count in [(0,8),(1,8),(6,8),(7,8),(2,5)]:
            with self.subTest(failure=failure,count=count):
                self.assertIsNone(infer(self.weekly(failure=failure,count=count)))

    def test_missing_week_shift_and_other_attempt_block_recovery(self):
        missing=[r for r in self.weekly() if r['row'] != 2]
        # Missing an internal week, rather than merely shortening the export.
        missing=[r for r in missing if r['row'] != 7]
        shifted=self.weekly()
        for r in shifted:
            if r['row'] in (6,7,8,9):r['time']+=timedelta(hours=2)
        extra=self.weekly()+[dict(time=datetime(2026,1,4,10),status='Succeeded',row=101)]
        for source in (missing,shifted,sorted(extra,key=lambda r:r['time'])):
            with self.subTest(source=source):
                self.assertIsNone(delayed_weekly_recovery(source))
                self.assertIsNone(infer(source))

    def test_recurring_secondary_runs_and_fast_runs_are_not_delayed_recoveries(self):
        for delay in (13, .5):
            source=[]
            for i in range(8):
                start=datetime(2026,1,2,20)+timedelta(weeks=i)
                source.extend([dict(time=start,status='Failed',row=i*2+2),
                               dict(time=start+timedelta(hours=delay),status='Succeeded',row=i*2+3)])
            model=infer(source)
            self.assertIsNone(delayed_weekly_recovery(source))
            self.assertEqual(model['interval'],delay*60)
            self.assertFalse(model['retries'])

    def test_unrelated_nonweekly_schedule_is_not_eligible_for_exception(self):
        source=self.weekly()
        origin=source[0]['time']
        for r in source:
            r['time']=origin+(r['time']-origin)/7
        self.assertIsNone(delayed_weekly_recovery(source))


if __name__ == '__main__':
    unittest.main()
