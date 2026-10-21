"""Derived timing values for the source-attempts dashboard, not scope decisions."""
from datetime import datetime
import json
import re


def feedback_sources(markdown):
    """Extract numbered sources from the feedback snapshot used by this run."""
    sections = {}
    pattern = r'^##\s+(\d+)\.\s+(.+?)\n(.*?)(?=^##\s|\Z)'
    for match in re.finditer(pattern, markdown, re.MULTILINE | re.DOTALL):
        number, title, body = match.groups()
        body = re.sub(r'^> ?', '', body.strip(), flags=re.MULTILINE).strip()
        sections[number] = {'title': title.strip(), 'text': body,
                            'named_flows': sorted(set(re.findall(r'\bwf_[A-Za-z0-9_]+\b', body)))}
    return sections


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.strip())
        # Match the analyzer's unspecified local-time convention; avoid host DST.
        return result if result.tzinfo is None else None
    except (ValueError, TypeError, AttributeError):
        return None


def attempt_timings(attempts):
    """Compare each attempt to the previous start-ordered attempt of this flow.

    A missing/invalid end does not mean the run finished or remained active.
    Original row references and every raw attempt (including duplicates) survive.
    """
    ordered = sorted(attempts, key=lambda a: (timestamp(a.get('start_time')) or datetime.max, a['row']))
    result = []
    previous = None
    for attempt in ordered:
        start, end = timestamp(attempt.get('start_time')), timestamp(attempt.get('end_time'))
        execution = (end - start).total_seconds() / 60 if start and end and end >= start else None
        gap = None
        overlap = 'N/A' if previous is None and start else 'Unknown'
        if previous and start:
            previous_start = timestamp(previous.get('start_time'))
            previous_end = timestamp(previous.get('end_time'))
            if previous_start and previous_end and previous_end >= previous_start:
                gap = (start - previous_end).total_seconds() / 60
                overlap = 'Yes' if gap < 0 else 'No'
        result.append({**attempt, 'plot_date': start.date().isoformat() if start else None,
                       'exec_minutes': execution, 'gap_minutes': gap,
                       'overlaps_previous': overlap,
                       'previous_row': previous['row'] if previous else None})
        previous = attempt
    return result


def dashboard_evidence(evidence):
    return {flow: {**entry, 'attempts': attempt_timings(entry.get('attempts', []))}
            for flow, entry in evidence.items()}


def file_activity_window(evidence):
    starts = [stamp for entry in evidence.values() for attempt in entry.get('attempts', [])
              for stamp in [timestamp(attempt.get('start_time'))] if stamp is not None]
    if not starts:
        return None
    first, last = min(starts), max(starts)
    return {'start': first.date().isoformat(), 'end': last.date().isoformat(),
            'start_time': first.isoformat(' '), 'end_time': last.isoformat(' '),
            'days': (last.date() - first.date()).days + 1}


def render_dashboard(template, results, evidence, manifest, feedback_text, outcomes):
    """Render inert, self-contained HTML from explicit inputs, with no file I/O."""
    data = {'results': results, 'evidence': dashboard_evidence(evidence),
            'activity_window': file_activity_window(evidence),
            'manifest': manifest, 'outcomes': outcomes,
            'feedback_sources': feedback_sources(feedback_text)}
    encoded = (json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
               .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))
    return template.replace('__PIPELINE_DATA__', encoded)
