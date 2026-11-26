"""Read-only funnel from 200 planned settings to independently admitted cases.

Counts only; never edits registry/ground truth and never imputes reviewer values.
"""
import json
from pathlib import Path

TARGET=200
REVIEW_DIR='results/review-handoff/prospective-review'
STATES=('admitted','approved_ready_to_apply','approved_record_incomplete','pending_review',
        'rejected_requires_new_attempt','not_captured')


def _load(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default


def review_record(root,candidate):
    """Reviewer's saved packet wins; otherwise the controller's blank packet."""
    packet=_load(root/REVIEW_DIR/(candidate+'.json')) or _load(root/'data/candidates'/candidate/'review-packet.json') or {}
    return packet.get('independent_review') or {}


def case_state(root,candidate):
    from scripts.apply_admission_review import validate_review
    ground=_load(root/'data/candidates'/candidate/'ground-truth.json',{})
    if ground.get('dataset_role')!='prospective_candidate' or ground.get('execution_status')!='captured_requires_review':
        return None
    if ground.get('admission_status')=='admitted':return 'admitted'
    record=review_record(root,candidate);decision=record.get('decision','pending')
    if decision=='rejected':return 'rejected_requires_new_attempt'
    if decision=='approved':
        try:validate_review(record);return 'approved_ready_to_apply'
        except (ValueError,TypeError):return 'approved_record_incomplete'
    return 'pending_review'


def progress(root):
    root=Path(root)
    plan=_load(root/'experiments/scenario-plan.json',{'scenarios':[]})['scenarios']
    registry=_load(root/'experiments/candidate-registry.json',{'attempts':[]})
    per={row['scenario_id']:{'scenario_id':row['scenario_id'],'split':row['split'],'variant':row['variant'],
                             'state':'not_captured','candidates':[]} for row in plan}
    rank={state:i for i,state in enumerate(STATES)}
    for attempt in registry['attempts']:
        row=per.get(attempt['scenario_id'])
        state=case_state(root,attempt['candidate_id']) if row else None
        if state is None:continue
        row['candidates'].append({'candidate_id':attempt['candidate_id'],'state':state})
        if rank[state]<rank[row['state']]:row['state']=state
    counts={state:sum(r['state']==state for r in per.values()) for state in STATES}
    captured=TARGET-counts['not_captured']
    return {'target':TARGET,'planned':len(per),'captured_scenarios':captured,'counts':counts,
            'admitted':counts['admitted'],'remaining_to_target':TARGET-counts['admitted'],
            'scenarios':list(per.values()),
            'note':'Scenario counts once even with replicate attempts. Rejected cases need a new attempt '
                   'under the frozen protocol; this tool does not retry or admit anything.'}
