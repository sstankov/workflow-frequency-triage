"""Source accounting and deterministic frequency policy regression tests."""
import csv
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from workflow_triage.analysis import analyze, calendar_pattern

ROOT = Path(__file__).resolve().parents[1]


class FrequencyTests(unittest.TestCase):
    def test_fixture_regressions(self):
        rows,evidence,_=analyze(ROOT/'_data/run_history.csv','test')
        flows={r['flow_id']:r for r in rows}
        self.assertEqual(len(flows),40)
        expected={
            'wf_SLS_ORDERS_INCR':('daily','MIGRATE'),
            'wf_INV_STOCK_HOURLY':('daily','MIGRATE'),
            'wf_WEB_CLICKS':('hourly','MIGRATE'),
            'wf_ERP_JRNL_15MIN':('hourly','MIGRATE'),
            'wf_PAY_AUTH_HOURLY':('every 30 minutes','TO ENGINEER'),
            'wf_TRD_POSITIONS':('every 15 minutes','TO ENGINEER'),
            'wf_FIN_MONTH_END_CLOSE':('monthly, last calendar day','MIGRATE'),
            'wf_BILL_INVOICE_WEEKLY':('monthly, first Monday–Friday day','MIGRATE'),
            'wf_FIN_BUDGET_ACTUALS':('monthly, third Monday–Friday day','MIGRATE'),
            'wf_HR_PAYROLL_MONTHLY':('monthly, day 25 moved to previous Monday–Friday day','MIGRATE'),
            'wf_FIN_QTR_REG_RPT':('unknown','UNKNOWN'),
            'wf_PROC_SUPPLIER_DAILY':('weekly','MIGRATE'),
            'wf_MKT_SEGMENT_REBUILD':('weekly','MIGRATE'),
            'wf_RISK_EXPOSURE_WKLY':('weekly','MIGRATE'),
        }
        for flow,result in expected.items():
            with self.subTest(flow=flow): self.assertEqual((flows[flow]['cadence'],flows[flow]['step1_outcome']),result)
        self.assertEqual(flows['wf_SLS_ORDERS_INCR']['probable_retry_count'],2)
        self.assertEqual(flows['wf_INV_STOCK_HOURLY']['probable_retry_count'],1)
        self.assertIn('possible_retirement_or_missing_history',flows['wf_MKT_CAMPAIGNS']['data_quality_flags'])
        for flow,recovery,failed in [('wf_MKT_SEGMENT_REBUILD',607,599),('wf_RISK_EXPOSURE_WKLY',524,516)]:
            self.assertEqual(flows[flow]['scheduled_occurrences'],13)
            self.assertEqual(flows[flow]['probable_retry_count'],1)
            self.assertIn('probable_delayed_recovery',flows[flow]['data_quality_flags'])
            self.assertIn('inferred, not confirmed',flows[flow]['step1_explanation'])
            self.assertEqual(evidence[flow]['retry_rows'],[recovery])
            self.assertEqual(evidence[flow]['delayed_recoveries'][0]['failed_row'],failed)
            self.assertEqual(len(evidence[flow]['attempts']),14)

    def analyze_rows(self,rows):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.csv'
            with path.open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['workflow_name','start_time','end_time','status']);w.writerows(rows)
            return analyze(path,'test')

    def test_invalid_empty_end_and_duplicates_are_accounted_for(self):
        source=[['good','2026-01-01 10:00:00','','Aborted'],['good','2026-01-01 10:00:00','','Aborted'],['good','bad','','Failed'],['invalid','n/a','','Stopped'],['','2026-01-01 12:00:00','','Succeeded']]
        rows,evidence,issues=self.analyze_rows(source)
        good=next(r for r in rows if r['flow_id']=='good')
        self.assertEqual(good['valid_unique_runs'],1)
        self.assertEqual(good['duplicate_rows'],1)
        self.assertEqual(good['invalid_rows'],1)
        self.assertEqual(good['missing_end_times'],1)
        self.assertEqual(good['step1_outcome'],'UNKNOWN')
        self.assertEqual(len(rows),3)
        self.assertEqual(sum(r['total_rows'] for r in rows),5)

    def test_sustained_55_minutes_is_never_rounded_to_hourly(self):
        starts=[datetime(2026,1,1)+timedelta(minutes=55*n) for n in range(60)]
        rows,_,_=self.analyze_rows([['arbitrary',str(s),'','Succeeded'] for s in starts])
        self.assertNotEqual(rows[0]['step1_outcome'],'MIGRATE')
        self.assertEqual(rows[0]['cadence'],'every 55 minutes')

    def test_partial_subhourly_schedule_is_not_hidden_by_daily_gaps(self):
        starts=[datetime(2026,1,d,8)+timedelta(minutes=30*n) for d in (1,2,3) for n in range(6)]
        rows,_,_=self.analyze_rows([['DAILY',str(s),'','Succeeded'] for s in starts])
        self.assertEqual(rows[0]['step1_outcome'],'TO ENGINEER')

    def test_first_weekday_monthly_is_inferred_from_dates_not_name(self):
        for dates in [('2026-07-01','2026-08-03','2026-09-01'),
                      ('2025-11-03','2025-12-01','2026-01-01'),
                      ('2026-01-01','2026-02-02','2026-03-02')]:
            with self.subTest(dates=dates):
                rows,_,_=self.analyze_rows([['misleading_HOURLY',d+' 05:00:00','','Succeeded'] for d in dates])
                row=rows[0]
                self.assertEqual(row['cadence'],'monthly, first Monday–Friday day')
                self.assertEqual(row['step1_outcome'],'MIGRATE')
                self.assertEqual(row['interval_minutes'],'')
                self.assertIn(dates[0],row['step1_explanation'])
                self.assertIn('holidays are not inferred',row['step1_explanation'])

    def test_nth_weekday_monthly_patterns(self):
        for dates,label in [(['2026-07-02','2026-08-04','2026-09-02'],'second'),
                            (['2026-07-03','2026-08-05','2026-09-03'],'third'),
                            (['2024-02-14','2024-03-14','2024-04-12'],'10th')]:
            with self.subTest(dates=dates):
                rows,_,_=self.analyze_rows([['unrelated_name',d+' 06:00:00','','Succeeded'] for d in dates])
                self.assertEqual(rows[0]['cadence'],'monthly, %s Monday–Friday day' % label)
                self.assertEqual(rows[0]['step1_outcome'],'MIGRATE')

    def test_nth_weekday_rejects_inconsistent_positions_and_weekends(self):
        for dates in [('2026-07-03','2026-08-06','2026-09-03'),
                      ('2026-07-04','2026-08-05','2026-09-03')]:
            with self.subTest(dates=dates):
                runs=[dict(time=datetime.fromisoformat(d+' 06:00'),status='Succeeded') for d in dates]
                self.assertIsNone(calendar_pattern(runs))

    def test_calendar_requires_consecutive_matching_months_and_consistent_clock(self):
        cases=[['2026-07-01 05:00','2026-08-03 05:00'],
               ['2026-07-01 05:00','2026-09-01 05:00','2026-10-01 05:00'],
               ['2026-07-01 05:00','2026-08-04 05:00','2026-09-01 05:00'],
               ['2026-07-01 05:00','2026-08-03 07:00','2026-09-01 05:00'],
               ['2026-07-01 05:00','2026-08-01 05:00','2026-09-02 05:00'],
               ['2026-07-01 05:00','2026-08-03 05:00','2026-08-03 05:30','2026-09-01 05:00']]
        for starts in cases:
            with self.subTest(starts=starts):
                runs=[dict(time=datetime.fromisoformat(s),status='Succeeded') for s in starts]
                self.assertIsNone(calendar_pattern(runs))

    def test_last_weekday_rule_does_not_accept_weekend_month_end(self):
        for starts,expected in [(['2026-07-31','2026-08-31','2026-09-30'],'monthly, last calendar day'),
                                (['2026-01-30','2026-02-27','2026-03-31'],'monthly, last business day'),
                                (['2026-01-30','2026-02-28','2026-03-31'],None)]:
            with self.subTest(starts=starts):
                model=calendar_pattern([dict(time=datetime.fromisoformat(s+' 05:00'),status='Succeeded') for s in starts])
                self.assertEqual(model['cadence'] if model else None,expected)

if __name__ == '__main__':
    unittest.main()
