"""LLM revision boundary: label-free packets and explicit candidate decisions."""
import json


def ambiguity_packet(tid,bank,candidates,chosen_id,static_rows,fold):
    """Candidates are already ranked by the calibrated decision utility, not golden."""
    chosen=next(c for c in candidates if c['id']==chosen_id)
    margin=candidates[0]['utility']-candidates[1]['utility'] if len(candidates)>1 else 1.0
    changed=sorted(map(tuple,chosen['rows']))!=sorted(map(tuple,static_rows))
    reasons=[]
    if chosen['full_probability']<.6:reasons.append('low_complete_payment_probability')
    if margin<.05:reasons.append('close_competing_hypotheses')
    if changed and margin<.15:reasons.append('model_static_disagreement')
    if not reasons:return None
    return dict(schema='v4.llm_revision.v1',bank_txn_id=tid,fold=fold,transaction=bank,
        selected_candidate_id=chosen_id,candidates=candidates[:3],reasons=reasons,
        priority=float(1-chosen['full_probability']+max(0,.15-margin)+.2*changed),
        allowed_actions=['KEEP','CHOOSE','EXTRACT_FACT','ABSTAIN'],
        instruction='Review source evidence and existing hypotheses. Do not invent IDs or amounts. Cite source spans for extracted facts. Golden labels and segment labels are not supplied.')


def revision_rows(packet,decision):
    """Apply only an explicit choice from this packet. New facts require regeneration."""
    if decision.get('bank_txn_id')!=packet['bank_txn_id']:
        raise ValueError('Revision belongs to another bank transaction')
    action=decision.get('action')
    if action in ('KEEP','ABSTAIN','EXTRACT_FACT'):
        key=packet['selected_candidate_id']
    elif action=='CHOOSE':
        key=decision.get('candidate_id')
        if not decision.get('reason','').strip():raise ValueError('Revision requires an explanation')
    else:raise ValueError('Unknown revision action')
    for candidate in packet['candidates']:
        if candidate['id']==key:return candidate['rows']
    raise ValueError('Unknown hypothesis; regenerate candidates for new extracted facts')
