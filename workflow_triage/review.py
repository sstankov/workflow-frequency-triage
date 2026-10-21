"""Pure review contract, decision assembly and human override policy."""
import json
import hashlib

OUTCOMES = ['MIGRATE', 'TO ENGINEER', 'UNKNOWN', 'DO NOT MIGRATE']
PROMPT_VERSION = '3.1'


def review_schema():
    props = {'flow_id':{'type':'string'},'final_cadence':{'type':'string'},'interval_minutes':{'type':['number','null']},'agent_outcome':{'type':'string','enum':OUTCOMES},'outcome_explanation':{'type':'string'},'comparison_explanation':{'type':'string'},'next_action':{'type':'string'},'evidence_rows':{'type':'array','items':{'type':'integer'}},'feedback_sections':{'type':'array','items':{'type':'integer'}}}
    return {'type':'object','properties':{'reviews':{'type':'array','items':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}},'required':['reviews'],'additionalProperties':False}


def validate_review(payload,step1):
    if not isinstance(payload,dict) or set(payload) != {'reviews'} or not isinstance(payload['reviews'],list):
        raise ValueError('Agent response must contain a reviews array')
    expected = {r['flow_id']:r for r in step1}
    reviews = payload['reviews']
    if any(not isinstance(r,dict) for r in reviews):
        raise ValueError('Every review must be an object')
    if len(reviews) != len(expected) or {r.get('flow_id') for r in reviews} != set(expected):
        raise ValueError('Agent must return every flow exactly once')
    required = set(review_schema()['properties']['reviews']['items']['properties'])
    for review in reviews:
        if set(review) != required:
            raise ValueError('Unexpected agent fields')
        source = expected[review['flow_id']]
        if review['agent_outcome'] not in {'MIGRATE','TO ENGINEER'}:
            raise ValueError('Completed review cannot be UNKNOWN or claim unconfirmed exclusion')
        for field in ('final_cadence','next_action','outcome_explanation','comparison_explanation'):
            if not isinstance(review[field],str) or len(review[field].strip()) < (40 if 'explanation' in field else 3):
                raise ValueError('Missing substantive '+field)
        interval = review['interval_minutes']
        if interval is not None and (type(interval) not in (int,float) or not 0 < interval < 1e9):
            raise ValueError('Invalid interval_minutes')
        if review['agent_outcome'] == 'MIGRATE' and ((interval is not None and interval < 60) or review['final_cadence'].lower() == 'unknown'):
            raise ValueError('MIGRATE contradicts the supplied cadence')
        rows = review['evidence_rows']
        if not isinstance(rows,list) or not rows or any(type(n) is not int or n not in source['evidence_rows'] for n in rows):
            raise ValueError('Evidence rows must reference this workflow')
        sections = review['feedback_sections']
        if not isinstance(sections,list) or any(type(n) is not int or n not in range(1,7) for n in sections):
            raise ValueError('Invalid feedback section')
    return {r['flow_id']:r for r in reviews}

def correction_id(flow_id, index, change):
    """Stable identity for old records as well as newly saved corrections."""
    if change.get('id'):
        return change['id']
    original = {key: change[key] for key in ('timestamp', 'outcome', 'cadence', 'reason', 'reviewer')}
    encoded = json.dumps([flow_id, index, original], sort_keys=True).encode()
    return 'legacy-' + hashlib.sha256(encoded).hexdigest()


def apply_overrides(results,overrides):
    known = {r['flow_id'] for r in results}
    for flow,history in overrides.items():
        if flow not in known: continue
        if not isinstance(history,list) or not history:
            raise ValueError('Override history must be a nonempty list')
        for change in history:
            if change.get('outcome') not in OUTCOMES or not all(isinstance(change.get(k),str) and change[k].strip() for k in ('reason','reviewer','timestamp','cadence')):
                raise ValueError('Invalid override record for '+flow)
            if ('removed_at' in change or 'removed_by' in change) and not all(
                    isinstance(change.get(k), str) and change[k].strip() for k in ('removed_at', 'removed_by')):
                raise ValueError('Invalid correction removal for '+flow)
    for row in results:
        history = overrides.get(row['flow_id'],[])
        row['override_history'] = [{**change, 'id': correction_id(row['flow_id'], index, change)}
                                   for index, change in enumerate(history)]
        row['final_outcome'] = row['agent_outcome']
        row['effective_explanation'] = row['outcome_explanation']
        row['effective_cadence'] = row['final_cadence']
        row['decision_source'] = 'agent' if row['review_complete'] else 'incomplete review'
        active = [change for change in history if not change.get('removed_at')]
        if active:
            change = active[-1]
            row['final_outcome'] = change['outcome']
            row['effective_explanation'] = 'Reviewer %s: %s' % (change['reviewer'],change['reason'])
            row['effective_cadence'] = change['cadence']
            row['decision_source'] = 'human override'
        row['outcome_changed'] = row['final_outcome'] != row['step1_outcome']
    return results


def incomplete_results(step1, reason):
    """Keep provisional decisions visible without presenting them as approved."""
    return [{
        **row,
        'final_cadence': row['cadence'],
        'final_interval_minutes': row['interval_minutes'],
        'agent_outcome': 'UNKNOWN',
        'review_complete': False,
        'agent_outcome_changed': row['step1_outcome'] != 'UNKNOWN',
        'outcome_explanation': 'Review incomplete: '+reason+' The provisional Python decision is not finalized.',
        'comparison_explanation': 'Step 1 proposed %s. A completed agent review is required before agreement or a change can be confirmed.' % row['step1_outcome'],
        'review_evidence_rows': [],
        'feedback_sections': [],
        'review_next_action': 'Complete the agent review and inspect any reported errors.',
    } for row in step1]


def reviewed_results(step1, reviews):
    """Join already-validated reviews by flow ID, preserving source row order."""
    results = []
    for row in step1:
        review = reviews[row['flow_id']]
        results.append({
            **row,
            'final_cadence': review['final_cadence'],
            'final_interval_minutes': review['interval_minutes'] if review['interval_minutes'] is not None else '',
            'agent_outcome': review['agent_outcome'],
            'review_complete': True,
            'agent_outcome_changed': review['agent_outcome'] != row['step1_outcome'],
            'outcome_explanation': review['outcome_explanation'],
            'comparison_explanation': review['comparison_explanation'],
            'review_evidence_rows': review['evidence_rows'],
            'feedback_sections': review['feedback_sections'],
            'review_next_action': review['next_action'],
        })
    return results


def build_review_prompt(template, step1_csv, feedback, evidence):
    return (template+'\n\nSTEP1_CSV\n'+step1_csv+'\n\nFEEDBACK\n'+feedback
            +'\n\nEVIDENCE_JSON\n'+json.dumps(evidence, ensure_ascii=False))
