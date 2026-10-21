"""Candidate-based cadence detection; timestamps are evidence, names are not."""
import calendar
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta

FAILURES = {'Failed', 'Aborted', 'Stopped'}

def month_weekday_number(stamp):
    """One-based Monday–Friday position in the month; no holiday assumptions."""
    if stamp.weekday() >= 5:
        return None
    return sum(stamp.replace(day=day).weekday() < 5 for day in range(1, stamp.day + 1))


def ordinal(number):
    words = {1: 'first', 2: 'second', 3: 'third'}
    suffix = 'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return words.get(number, '%s%s' % (number, suffix))


def make_model(label, runs, retries, family, interval=None, cycle_days=None):
    return dict(cadence=label, interval=interval, runs=runs, retries=retries,
                calendar=family == 'calendar', family=family, cycle_days=cycle_days)


def collapse_calendar_retries(runs):
    base, retries = [], []
    for i, run in enumerate(runs):
        # Do not collapse after a successful retry or across an intervening run.
        if i and runs[i-1]['status'] in FAILURES and base and run['time'].date() == base[-1]['time'].date() and (run['time'] - base[-1]['time']).total_seconds() <= 21600:
            retries.append(run)
        else:
            base.append(run)
    return base, retries


def adjusted_month_date(stamp, day, direction):
    date = stamp.replace(day=min(day, calendar.monthrange(stamp.year, stamp.month)[1]))
    if direction == 'previous':
        while date.weekday() >= 5:
            date -= timedelta(days=1)
    elif direction == 'next':
        while date.weekday() >= 5:
            date += timedelta(days=1)
    elif date.weekday() == 5:
        date -= timedelta(days=1)
    elif date.weekday() == 6:
        date += timedelta(days=1)
    # Cross-month shifts are ambiguous without knowing the nominal schedule month.
    return date.date() if date.month == stamp.month else None


def calendar_models(runs):
    base, retries = collapse_calendar_retries(runs)
    dates = [r['time'] for r in base]
    if len(dates) < 3:
        return []
    clock = [d.hour * 60 + d.minute + d.second / 60 for d in dates]
    if max(clock) - min(clock) > 20:
        return []
    months = [d.year * 12 + d.month for d in dates]
    unique_months = sorted(set(months))
    steps = {b-a for a,b in zip(unique_months, unique_months[1:])}
    if len(unique_months) < 3 or len(steps) != 1 or next(iter(steps)) not in {1,2,3,6,12}:
        return []
    step = next(iter(steps))
    prefix = {1:'monthly',2:'every two months',3:'quarterly',6:'every six months',12:'annually'}[step]
    models = []
    def add(label, fits):
        if fits:
            models.append(make_model(prefix + ', ' + label, base, retries, 'calendar', cycle_days=31*step))
    if len(months) == len(unique_months):
        lengths = [calendar.monthrange(d.year, d.month)[1] for d in dates]
        offsets = {length-d.day for d,length in zip(dates,lengths)}
        weekdays = {month_weekday_number(d) for d in dates}
        reverse_weekdays = {sum(d.replace(day=day).weekday() < 5 for day in range(d.day,length+1)) if d.weekday()<5 else None for d,length in zip(dates,lengths)}
        add('last calendar day', offsets == {0})
        add('day %s' % dates[0].day, len({d.day for d in dates}) == 1)
        add('last business day', reverse_weekdays == {1})
        if None not in weekdays and len(weekdays) == 1:
            add('%s Monday–Friday day' % ordinal(next(iter(weekdays))), True)
        if None not in reverse_weekdays and len(reverse_weekdays) == 1:
            add('%s Monday–Friday day from month end' % ordinal(next(iter(reverse_weekdays))), True)
        add('last %s' % dates[0].strftime('%A'), len({d.weekday() for d in dates}) == 1 and all((d+timedelta(days=7)).month != d.month for d in dates))
        add('weekday %s occurrence %s' % (dates[0].strftime('%A'), (dates[0].day-1)//7+1), len({(d.weekday(),(d.day-1)//7) for d in dates}) == 1)
        if len(offsets) == 1 and offsets != {0}:
            add('%s days before month end' % next(iter(offsets)), True)
        for direction in ('previous','next','nearest'):
            for day in range(1,32):
                add('day %s moved to %s Monday–Friday day' % (day,direction),
                    all(adjusted_month_date(d,day,direction) == d.date() for d in dates))
    else:
        by_month = defaultdict(list)
        for date, month in zip(dates,months):
            by_month[month].append(date.day)
        sets = list(by_month.values())
        # A small repeated set, not an arbitrary memorized month's daily history.
        if 2 <= len(sets[0]) <= 4 and len(set(sets[0])) == len(sets[0]) and all(days == sets[0] for days in sets):
            days = ' and '.join(map(str,sets[0]))
            label = ('twice monthly' if step == 1 and len(sets[0]) == 2 else prefix) + ', days ' + days
            models.append(make_model(label,base,retries,'calendar',cycle_days=31*step))
    return models


def calendar_pattern(runs):
    models = calendar_models(runs)
    return models[0] if models else None


def fit_period(runs, period, daily_reset=False):
    if len(runs) < 3:
        return None
    tolerance = 10 if period >= 60 else min(2, period * .1)
    values = [(r['time'] - datetime(1970, 1, 1)).total_seconds() / 60 for r in runs]
    if daily_reset:
        values = [v % 1440 for v in values]
    # Pick the observed phase with the most in-tolerance starts.
    ref = max(values, key=lambda ref: sum(abs((v-ref+period/2) % period-period/2) <= tolerance for v in values))
    assigned, retries, slots = [], [], set()
    for i, (run, value) in enumerate(zip(runs, values)):
        slot = round((value-ref) / period)
        slot_key = (run['time'].date(), slot) if daily_reset else slot
        residual = abs(value-ref-slot*period)
        if residual <= tolerance and slot_key not in slots:
            assigned.append(run)
            slots.add(slot_key)
        elif i and runs[i-1]['status'] in FAILURES and (run['time']-runs[i-1]['time']).total_seconds()/60 <= min(360, period/2):
            retries.append(run)
        else:
            return None
    if len(assigned) < 3:
        return None
    counts = Counter(r['time'].date() for r in assigned).values()
    if period < 1440 and not (sum(count >= 3 for count in counts) >= 2 or sum(count >= 2 for count in counts) >= 3):
        return None
    gaps = [(b['time']-a['time']).total_seconds()/60 for a,b in zip(assigned,assigned[1:]) if period >= 1440 or a['time'].date() == b['time'].date()]
    if not gaps or sum(abs(g-period) <= tolerance*2 for g in gaps) < max(2, len(gaps)*.5):
        return None
    labels = {15:'every 15 minutes',30:'every 30 minutes',60:'hourly',1440:'daily',10080:'weekly',20160:'every two weeks'}
    label = labels.get(period, 'every %g minutes' % period)
    if period == 1440 and len({r['time'].weekday() for r in assigned}) >= 4 and all(r['time'].weekday() < 5 for r in assigned):
        label = 'daily, weekdays'
    if daily_reset:
        label += ' during daily active window'
    model = make_model(label, assigned, retries, 'interval', interval=period, cycle_days=period/1440)
    model['residual'] = statistics.mean(abs((v-ref+period/2) % period-period/2) for v in values)
    model['direct_gap_ratio'] = sum(abs(g-period) <= tolerance*2 for g in gaps)/len(gaps)
    return model


def clock_models(runs):
    """Repeated daily or weekly sets of clock slots, including uneven spacing."""
    if len(runs) < 3:
        return []
    models = []
    for family, length, minimum_slots in [('daily clock',1440,2),('weekly clock',10080,1)]:
        origin = datetime(1970,1,5)  # Monday
        values = [(r['time']-origin).total_seconds()/60 for r in runs]
        phases = sorted((value % length, i) for i,value in enumerate(values))
        clusters = []
        for phase, index in phases:
            if not clusters or phase-clusters[-1][0][0] > 20:
                clusters.append([])
            clusters[-1].append((phase,index))
        if not minimum_slots <= len(clusters) <= 14:
            continue
        centers = [statistics.median(v for v,_ in cluster) for cluster in clusters]
        cycles = defaultdict(list)
        for slot,cluster in enumerate(clusters):
            for _,index in cluster:
                cycles[int(values[index]//length)].append(slot)
        # Every slot must recur for at least three cycles; partial cycles do not
        # create new rules. Interval matching independently tolerates missing slots.
        expected = list(range(len(clusters)))
        if len(cycles) < 3 or any(sorted(slots) != expected for slots in cycles.values()):
            continue
        cycle_ids = sorted(cycles)
        coverage = len(cycles)/(cycle_ids[-1]-cycle_ids[0]+1)
        if coverage < (.65 if family == 'daily clock' else 1):
            continue
        if family == 'weekly clock' and len(centers) == 1:
            continue  # Already covered by interval matching.
        gaps = [b-a for a,b in zip(centers, centers[1:]+[centers[0]+length])]
        interval = round(min(gaps), 3)
        if interval < 60:
            # Hourly jitter also creates clock clusters with short median gaps.
            # A sub-hourly clock claim needs the same close pair on every cycle
            # with the tighter sub-hourly tolerance, not just a short average.
            pair = gaps.index(min(gaps))
            if pair == len(centers)-1:
                continue
            left = {int(values[i]//length):v for v,i in clusters[pair]}
            right = {int(values[i]//length):v for v,i in clusters[pair+1]}
            pair_gaps = [right[c]-left[c] for c in cycles]
            tolerance = min(2, interval*.1)
            if any(g >= 60 or abs(g-interval)>tolerance for g in pair_gaps):
                continue
        # Remove seconds-level jitter only at the minute boundary. Never round
        # a sustained 55/59-minute pattern to hourly.
        if abs(interval-round(interval)) <= 1/60:
            interval = round(interval)
        def describe(value):
            minute = int(round(value)) % length
            clock = '%02d:%02d' % ((minute%1440)//60,minute%60)
            return (['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][minute//1440]+' ' if family == 'weekly clock' else '')+clock
        label = ('daily' if family == 'daily clock' else 'weekly')+' at '+', '.join(describe(c) for c in centers)
        if family == 'daily clock' and all(r['time'].weekday()<5 for r in runs):
            label = label.replace('daily at','weekdays at')
        model = make_model(label,runs,[],family,interval=interval,cycle_days=length/1440)
        models.append(model)
    return models


def interval_candidates(runs):
    # Common intervals plus data-derived repeated gaps: no per-workflow rules.
    candidates = {1,5,10,15,20,30,45,60,90,120,180,240,360,480,720,1440,2880,10080,20160}
    gaps = [(b['time']-a['time']).total_seconds()/60 for a,b in zip(runs,runs[1:])]
    for gap,count in Counter(round(g) for g in gaps if g >= 1).items():
        if count >= 2:
            candidates.add(gap)
    for gap,count in Counter(round(g, 3) for g in gaps if g >= 1).items():
        if count >= 3:
            candidates.add(gap)
    return sorted(candidates)


def delayed_weekly_recovery(runs):
    """One isolated next-day recovery, bracketed by an intact weekly schedule."""
    candidates = []
    for index in range(1, len(runs)):
        previous, recovery = runs[index-1:index+1]
        delay = (recovery['time']-previous['time']).total_seconds()/60
        if previous['status'] in FAILURES and recovery['status'] == 'Succeeded' and 360 < delay <= 1440:
            candidates.append((index, delay))
    if len(candidates) != 1:
        return None
    index, delay = candidates[0]
    retained = runs[:index] + runs[index+1:]
    # The failed occurrence needs at least two scheduled starts on each side.
    failure_index = index-1
    if len(retained) < 6 or failure_index < 2 or len(retained)-failure_index-1 < 2:
        return None
    model = fit_period(retained, 10080)
    if not model or model['retries'] or model['direct_gap_ratio'] != 1:
        return None
    # No other unmatched attempts, skipped weeks or recurring secondary slots.
    recovery, failure = runs[index], runs[index-1]
    model['retries'] = [recovery]
    model['delayed_recoveries'] = [{
        'row': recovery['row'], 'failed_row': failure['row'],
        'delay_minutes': round(delay, 3),
        'preceding_scheduled_rows': [r['row'] for r in retained[failure_index-2:failure_index]],
        'following_scheduled_rows': [r['row'] for r in retained[failure_index+1:failure_index+3]],
    }]
    return model


def infer(runs):
    if len(runs) < 3:
        return None
    models = calendar_models(runs) + clock_models(runs)
    for period in interval_candidates(runs):
        for reset in ([False,True] if period < 1440 and 1440 % period else [False]):
            model = fit_period(runs,period,reset)
            if model:
                models.append(model)
    recovery_model = delayed_weekly_recovery(runs)
    if recovery_model:
        models.append(recovery_model)
    if not models:
        return None
    # Explain as many actual attempts as scheduled starts as possible before
    # assuming retries. Prefer an explicit calendar rule over a coincidental
    # interval, then the best interval alignment over a more complex slot set.
    family_priority = {'calendar':0,'interval':1,'daily clock':2,'weekly clock':3}
    models.sort(key=lambda m:(len(m['retries']),3 if m['family']=='interval' and m['direct_gap_ratio']<.8 else family_priority[m['family']],m.get('residual',0)))
    selected = models[0]
    selected['matching_patterns'] = list(dict.fromkeys(m['cadence'] for m in models))
    # A supported faster schedule must not be hidden by a slower model that
    # dismisses those same attempts as retries.
    fastest = [m for m in models if m['interval'] is not None and m['interval'] < 60 and len(m['retries']) <= len(selected['retries'])]
    if fastest and (selected['interval'] is None or selected['interval'] >= 60):
        selected = fastest[0]
        selected['matching_patterns'] = list(dict.fromkeys(m['cadence'] for m in models))
    return selected


def unresolved_reason(runs):
    if len(runs) < 3:
        return 'Cadence not determined: %s valid unique start%s; at least three repeated occurrences are needed to assess a recurring pattern.' % (len(runs), '' if len(runs)==1 else 's')
    return ('Cadence not determined: no supported interval, daily/weekly clock pattern or calendar rule explains all %s starts with sufficient repetition and supported retry grouping. '
            'This may reflect irregular execution, a schedule change, missing history or an unsupported calendar; request schedule configuration or fuller history.' % len(runs))
