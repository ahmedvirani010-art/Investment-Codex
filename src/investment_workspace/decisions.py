"""User decisions and factual transaction links; never order creation."""
from copy import deepcopy
from decimal import Decimal
from .storage import digest,dumps
from .record_history import accept_records
from .runtime import assessment_date,json_values


BASIS_VERSION='ic-reviewed-basis-v2'
_NON_MATERIAL={'run_id','upstream_run_ids','code_hash','code_version','input_hash','schema_version'}


def _material(value):
    """Canonical risk inputs/results, excluding calculation-only lineage."""
    if isinstance(value,dict):
        return {k:_material(v) for k,v in value.items() if k not in _NON_MATERIAL}
    if isinstance(value,list):
        return sorted((_material(v) for v in value),key=lambda v:dumps(json_values(v)))
    return value


def basis(state,ticker):
    integration=state.get('integration',{})
    inputs=integration.get('input',{})
    model=next((m for m in state.get('research',{}).get('input',{}).get('models',[]) if m['ticker']==ticker),None)
    holdings=[{k:h.get(k) for k in ('ticker','sector','quantity','price','price_date','market_value','reconciliation_state')}
              for h in state.get('holdings',[])]
    coverage=[{k:r.get(k) for k in ('ticker','outcome','reason')} for r in state.get('coverage',[]) if r.get('ticker')==ticker]
    timing=[{k:r.get(k) for k in ('status','latest_session','stage','rs_percentile','extended')} for r in integration.get('timing',[]) if r.get('ticker')==ticker]
    history_refs=[{k:r.get(k) for k in ('record_id','ticker','effective_date','valid_until','source_ids')}
                  for r in inputs.get('histories',[])]
    risk_inputs={'limits':inputs.get('risk_limits'),'factors':inputs.get('factors',[]),
                 'timing_policy':inputs.get('timing_policy'),'history_versions':history_refs,
                 'candidates':[r for r in inputs.get('candidates',[]) if r.get('ticker')==ticker]}
    sizing=[r.get('sizing') for r in integration.get('ic_actions',[]) if r.get('ticker')==ticker]
    portfolio={k:state.get('summary',{}).get(k) for k in ('cash','total_assets','hhi','effective_positions')}
    return digest(dumps(json_values({'basis_version':BASIS_VERSION,'model':model,'holdings':_material(holdings),
        'portfolio':portfolio,'coverage':_material(coverage),'timing':_material(timing),
        'risk_inputs':_material(risk_inputs),'risk':_material(integration.get('risk',[])),
        'correlations':_material(integration.get('correlations',[])),'sizing':_material(sizing)})))


def calculate(bundle,state,previous,run_id,input_hash):
    history=accept_records({'decisions':bundle.decisions},previous.get('decisions',{}),bundle,run_id,input_hash)
    if not bundle.decisions and not history: return
    proposals={p.record_id:p for p in bundle.integration.proposals} if bundle.integration else {}
    prior_proposals={h['record_id']:h['payload'] for h in state.get('integration',{}).get('history',[]) if h['group']=='proposals'}
    sources={s.source_id:s for s in bundle.sources}; transactions={t['transaction_id']:t for t in state['transactions']}
    rows=[];used=set()
    for d in bundle.decisions:
        p=proposals.get(d.proposal_id)
        old=prior_proposals.get(d.proposal_id)
        if old is None or old['ticker']!=d.ticker: raise ValueError('decision proposal must resolve to same ticker')
        action=old['action'];direction={'ADD':'BUY','ACCUMULATE':'BUY','TRIM':'SELL','EXIT':'SELL'}.get(action)
        linked=[]
        for tid in d.transaction_ids:
            t=transactions.get(tid)
            if t is None or tid in used or t.get('ticker')!=d.ticker or t.get('kind')!=direction:
                raise ValueError('decision transaction link has wrong owner, ticker or direction')
            from datetime import datetime
            if datetime.fromisoformat(t['timestamp'])<d.decided_at: raise ValueError('execution cannot predate approval')
            used.add(tid);linked.append(t)
        current_hash=basis(state,d.ticker)
        reviewed=bool(p and current_hash==d.reviewed_basis_hash and d.valid_until>=assessment_date(bundle)
                      and all(sources[s].evidence_label=='CONFIRMED' for s in d.source_ids))
        quantity=sum((Decimal(t['quantity']) for t in linked),Decimal(0))
        execution='NOT_EXECUTED' if not linked else 'LINKED_TRANSACTIONS'
        if linked and d.approved_quantity is not None:
            execution='EXECUTION_EXCEPTION' if quantity>d.approved_quantity else 'EXECUTED' if quantity==d.approved_quantity else 'PARTIALLY_EXECUTED'
        rows.append({**d.model_dump(mode='json'),'owner':'user_decision','run_id':run_id,'schema_version':'6.0',
                     'model_version':'ic-decision-v2','basis_version':BASIS_VERSION,'assumption_ids':[d.proposal_id],
                     'upstream_run_ids':sorted({h['run_id'] for h in state.get('integration',{}).get('history',[]) if h['record_id']==d.proposal_id}),
                     'basis_hash':current_hash,'review_status':'CURRENT' if reviewed else 'NEEDS_REVIEW',
                     'execution_status':execution,'linked_quantity':quantity,'proposal_action':action,'orders_created':False})
        if d.decision=='APPROVE' and not reviewed:
            state['data_gaps'].append({'ticker':d.ticker,'field':'ic_decision','owner':'user_decision','reason':'DECISION_NEEDS_REVIEW','next_action':'Review changed model, holdings or risk basis'})
    old_rows={r['record_id']:r for r in previous.get('decisions',{}).get('rows',[])}
    for i,row in enumerate(rows):
        old=old_rows.get(row['record_id'])
        if old and {k:v for k,v in old.items() if k not in {'run_id','code_version','code_hash'}}==json_values({k:v for k,v in row.items() if k not in {'run_id','code_version','code_hash'}}): rows[i]=deepcopy(old)
    state['decisions']={'input':{'decisions':[d.model_dump(mode='json') for d in bundle.decisions]},'history':history,'rows':json_values(rows)}
