"""Deterministic evidence extraction. No workflow-name based classification."""
import csv
import statistics
from collections import Counter, defaultdict
from datetime import datetime

RULE_VERSION = '3.1'
from .cadence import FAILURES, infer, calendar_pattern, unresolved_reason


def parse_time(value):
    stamp = datetime.fromisoformat(value.strip())
    if stamp.tzinfo is not None:
        raise ValueError('Timezone-aware timestamps require normalization before this prototype')
    return stamp


def analyze(path, run_id):
    grouped, issues, all_times = defaultdict(list), [], []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        required = {'workflow_name','start_time','end_time','status'}
        if not required <= set(reader.fieldnames or []):
            raise ValueError('CSV must include: '+', '.join(sorted(required)))
        for number, row in enumerate(reader,2):
            flow = (row.get('workflow_name') or '').strip() or '__MISSING_ID_ROW_%s' % number
            item = {'row':number, **{k:row.get(k) or '' for k in required}}
            item['flow_id'] = flow
            try:
                item['time'] = parse_time(item['start_time'])
                all_times.append(item['time'])
            except (ValueError, TypeError):
                item['time'] = None
                issues.append({'row':number,'flow_id':flow,'issue':'invalid_start_time'})
            if flow.startswith('__MISSING_ID_ROW_'):
                issues.append({'row':number,'flow_id':flow,'issue':'missing_workflow_id'})
            grouped[flow].append(item)
    boundary = max(all_times) if all_times else None
    results, evidence = [], {}
    for flow, items in sorted(grouped.items()):
        seen, runs, duplicates = set(), [], []
        for item in items:
            key = tuple(item[k] for k in ('workflow_name','start_time','end_time','status'))
            if key in seen:
                duplicates.append(item['row'])
                issues.append({'row':item['row'],'flow_id':flow,'issue':'exact_duplicate'})
            elif item['time']:
                runs.append(item)
            seen.add(key)
        runs.sort(key=lambda r:r['time'])
        model = infer(runs)
        flags = []
        invalid = sum(r['time'] is None for r in items)
        if invalid: flags.append('invalid_start_time')
        if duplicates: flags.append('duplicate_rows')
        if any(not r['end_time'] for r in items): flags.append('missing_end_time')
        if any(r['status'] not in {'Succeeded',*FAILURES} for r in items): flags.append('unrecognized_status')
        if flow.startswith('__MISSING_ID_ROW_'): flags.append('missing_workflow_id')
        window = (runs[-1]['time']-runs[0]['time']).total_seconds()/86400 if runs else 0
        if window < 7: flags.append('short_history')
        inactive = (boundary-runs[-1]['time']).total_seconds()/86400 if runs and boundary else None
        if model and model['retries']: flags.append('probable_retries')
        if model and model.get('delayed_recoveries'): flags.append('probable_delayed_recovery')
        if runs and all(r['status'] != 'Succeeded' for r in runs): flags.append('no_successful_runs')
        stale_limit = max(14, 3*(model.get('cycle_days') or 31)) if model else 93
        if inactive is not None and inactive > stale_limit: flags.append('possible_retirement_or_missing_history')
        if model:
            cadence, interval = model['cadence'], model['interval']
            status = 'TO ENGINEER' if interval is not None and interval < 60 else 'MIGRATE'
            reason = '%s scheduled occurrences support %s within the observed window.' % (len(model['runs']),cadence)
            if model['calendar']:
                dates = [r['time'] for r in model['runs']]
                reason += ' Matching starts: %s; observed start times %s–%s (within the 20-minute calendar tolerance).' % (', '.join(d.strftime('%Y-%m-%d') for d in dates), min(d.strftime('%H:%M:%S') for d in dates), max(d.strftime('%H:%M:%S') for d in dates))
                if 'Monday–Friday' in cadence or 'business day' in cadence:
                    reason += ' Weekdays mean Monday–Friday; holidays are not inferred from this export.'
            if model['retries']:
                reason += ' %s probable retry attempt%s %s a failed/stopped/aborted attempt outside the expected slot.' % (len(model['retries']), '' if len(model['retries']) == 1 else 's', 'follows' if len(model['retries']) == 1 else 'follow')
            for recovery in model.get('delayed_recoveries',[]):
                hours, minutes = divmod(round(recovery['delay_minutes']), 60)
                reason += (' Row %s is a probable delayed recovery of row %s, %sh %sm later. '
                           'The other %s starts form an uninterrupted weekly schedule, with at least two scheduled occurrences before and after the failed occurrence. '
                           'This isolated successful recovery is within 24 hours; the retry relationship is inferred, not confirmed by a run identifier.'
                           % (recovery['row'], recovery['failed_row'], hours, minutes, len(model['runs'])))
            if interval == 60 and model['family'] == 'interval':
                reason += ' Starts fit hourly slots within the 10-minute tolerance; short jitter gaps are not extra schedule occurrences.'
            if model['family'] in {'daily clock','weekly clock'}:
                reason += ' The shortest recurring gap between clock slots is %g minutes.' % interval
            if len(model.get('matching_patterns',[])) > 1:
                reason += ' Other supported patterns also fit these observations; the exact scheduler configuration is not uniquely established.'
            reason += ' The recurring cadence is %s the hourly migration boundary.' % ('faster than' if status == 'TO ENGINEER' else 'at or slower than')
        else:
            cadence,interval,status = 'unknown',None,'UNKNOWN'
            reason = unresolved_reason(runs)
        if any(f in flags for f in ('invalid_start_time','missing_workflow_id','possible_retirement_or_missing_history')):
            status = 'UNKNOWN'
            reason += ' Missing/invalid evidence or a long trailing gap leaves current eligibility unresolved.'
        next_action = {'MIGRATE':'Validate the provisional cadence against feedback.','TO ENGINEER':'Review evidence, then ask an engineer to scope the sub-hourly schedule.','UNKNOWN':'Review feedback and request schedule configuration if uncertainty remains.'}[status]
        gaps = [(b['time']-a['time']).total_seconds()/60 for a,b in zip(runs,runs[1:])]
        evidence[flow] = {
            'attempts':[{k:v for k,v in r.items() if k != 'time'} for r in items],
            'retry_rows':[r['row'] for r in model['retries']] if model else [],
            'delayed_recoveries':model.get('delayed_recoveries',[]) if model else [],
            'scheduled_rows':[r['row'] for r in model['runs']] if model else [],
            'cadence_detection':{'family':model['family'] if model else 'unresolved','matching_patterns':model.get('matching_patterns',[]) if model else []},
            'daily_counts':dict(sorted(Counter(r['start_time'][:10] for r in runs).items())),
            'gaps_minutes':[round(g,3) for g in gaps],
        }
        results.append(dict(run_id=run_id,flow_id=flow,observed_start=runs[0]['start_time'] if runs else '',observed_end=runs[-1]['start_time'] if runs else '',observed_window_days=round(window,3),export_end=boundary.isoformat(' ') if boundary else '',total_rows=len(items),valid_unique_runs=len(runs),invalid_rows=invalid,duplicate_rows=len(duplicates),failed_runs=sum(r['status'] in FAILURES for r in runs),missing_end_times=sum(not r['end_time'] for r in runs),probable_retry_count=len(model['retries']) if model else 0,scheduled_occurrences=len(model['runs']) if model else '',delayed_recoveries=model.get('delayed_recoveries',[]) if model else [],cadence=cadence,cadence_family=model['family'] if model else 'unresolved',matching_patterns=model.get('matching_patterns',[]) if model else [],interval_minutes=interval if interval is not None else '',active_window=('%s–%s' % (min(r['time'].strftime('%H:%M') for r in runs),max(r['time'].strftime('%H:%M') for r in runs))) if runs else '',median_gap_minutes=round(statistics.median(gaps),3) if gaps else '',min_gap_minutes=round(min(gaps),3) if gaps else '',inactive_days=round(inactive,3) if inactive is not None else '',data_quality_flags=flags,evidence_rows=[r['row'] for r in items],step1_outcome=status,step1_explanation=reason,next_action=next_action,rule_version=RULE_VERSION))
    return results,evidence,issues
