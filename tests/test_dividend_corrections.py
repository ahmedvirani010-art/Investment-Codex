"""Phase 1: corrections must use revised proof without losing historical entitlement."""
import json
from copy import deepcopy
from datetime import datetime,timezone,date
from decimal import Decimal

import pytest
from investment_workspace import pipeline
from investment_workspace.schemas import Bundle
from investment_workspace.storage import dumps,read_json,committed
from investment_workspace.portfolio import calculate
from investment_workspace.dividends import result


@pytest.fixture
def full():
    return json.loads(pipeline.fixture_bytes(completion=True))


def original(full):
    b=Bundle.model_validate(full);state=calculate(b);d=b.research.dividends[0]
    return b,state,d,result(d,b,state,{'run_id':'original'},lambda _:True)


def test_pipeline_recalculates_corrected_quantity_and_keeps_both_bases(repo,full):
    initial=pipeline.run(repo,dumps(full));assert initial['status']!='FAILED'
    frozen=committed(repo,'runs/'+initial['run_id']+'/snapshot.json')
    prior=read_json(repo,pipeline.STATE)['research']
    before=prior['dividends'][0]
    x=deepcopy(full)
    def source(source_id,tag):
        s=deepcopy(next(s for s in x['sources'] if s['source_id']==source_id))
        s['source_id']='synthetic.correction.'+tag;x['sources'].append(s);return s['source_id']
    for name in ('opening','closing'):
        x[name]['source_id']=source(x[name]['source_id'],name)
        p=next(p for p in x[name]['positions'] if p['ticker']=='DEMO-BANK')
        p['quantity']=str(Decimal(p['quantity'])+50);p['cost']=str(Decimal(p['cost'])+5000)
    d=x['research']['dividends'][0];d.update(supersedes=d['record_id'],record_id='corrected.dividend',source_ids=[source(d['source_ids'][0],'announcement')])
    attempt=pipeline.run(repo,dumps(x));assert attempt['status']!='FAILED',attempt
    state=read_json(repo,pipeline.STATE);row=state['research']['dividends'][0]
    assert Decimal(row['eligible_quantity'])==150 and Decimal(row['gross_entitlement'])==375
    assert row['status']=='PARTIALLY_RECEIVED' and Decimal(row['net_pending'])==100
    assert row['entitlement_basis']['basis_id']!=before['entitlement_basis']['basis_id']
    assert len(state['research']['entitlements'])==len(prior['entitlements'])+1
    assert before['entitlement_basis'] in state['research']['entitlements']
    assert state['reconciliation']==[] and state['summary']['cash']=='15220.00'
    assert committed(repo,'runs/'+initial['run_id']+'/snapshot.json')==frozen
    assert pipeline.validate(repo)['workbook_parity']=='PASS'
    basis=deepcopy(row['entitlement_basis'])
    pipeline.run(repo,dumps(x))
    assert read_json(repo,pipeline.STATE)['research']['dividends'][0]['entitlement_basis']==basis


def test_corrected_supporting_transaction_changes_entitlement(full):
    b,state,d,old=original(full)
    seller=next(t for t in b.transactions if t.kind=='SELL' and t.ticker==d.ticker)
    seller.settlement_date=date(2026,10,8)
    revised=d.model_copy(update={'record_id':'settlement.correction','supersedes':d.record_id,'revision_kind':'ENTITLEMENT_BASIS'})
    state=calculate(b);assert state['reconciliation']==[]
    row=result(revised,b,state,{},lambda _:True,{'dividends':[old]})
    assert Decimal(row['eligible_quantity'])==80
    assert row['entitlement_basis']['basis_id']!=old['entitlement_basis']['basis_id']
    assert row['status']=='RECEIPT_EXCEPTION'  # original gross receipt now exceeds entitlement


@pytest.mark.parametrize('cause',['missing_window','unverified','unreconciled'])
def test_unavailable_correction_keeps_proof_and_stays_pending(full,cause):
    b,state,d,old=original(full)
    d=d.model_copy(update={'record_id':'basis.correction','supersedes':d.record_id,'revision_kind':'ENTITLEMENT_BASIS'})
    verified=lambda _:True
    if cause=='missing_window': b.opening.timestamp=datetime(2026,10,10,tzinfo=timezone.utc)
    if cause=='unverified': verified=lambda _:False
    if cause=='unreconciled': state['reconciliation']=[{'reason':'unreconciled evidence'}]
    row=result(d,b,state,{},verified,{'dividends':[old]})
    assert row['status']=='CORRECTION_PENDING' and row['entitlement_basis'] is None
    assert row['previous_verified_result']==old and row['net_pending'] is None
    again=result(d,b,state,{},verified,{'dividends':[row]})
    assert again['status']=='CORRECTION_PENDING' and again['previous_verified_result']==old


def test_later_receipt_carries_unchanged_basis_after_window_and_review_expire(full):
    b,state,d,_=original(full)
    announced=d.model_copy(update={'receipt_transaction_ids':[]})
    old=result(announced,b,state,{},lambda _:True)
    assert old['status']=='RECEIVABLE'
    updated=d.model_copy(update={'record_id':'receipt.update','supersedes':d.record_id,'revision_kind':'RECEIPT_UPDATE','valid_until':date(2026,10,8)})
    b.opening.timestamp=datetime(2026,10,10,tzinfo=timezone.utc)
    row=result(updated,b,state,{},lambda _:True,{'dividends':[old]})
    assert row['status']=='RECEIVED' and Decimal(row['net_pending'])==0
    assert row['entitlement_basis']==old['entitlement_basis']
    assert state['summary']['cash']=='15220.00'


def test_unchanged_evidence_does_not_replace_basis(full):
    b,state,d,old=original(full)
    d=d.model_copy(update={'record_id':'unchanged','supersedes':d.record_id})
    row=result(d,b,state,{},lambda _:True,{'dividends':[old]})
    assert row['entitlement_basis']==old['entitlement_basis']


def test_receipt_update_rejects_changed_terms(full):
    b,state,d,old=original(full)
    d=d.model_copy(update={'record_id':'bad.receipt','supersedes':d.record_id,'revision_kind':'RECEIPT_UPDATE','dps':Decimal(3)})
    with pytest.raises(ValueError,match='receipt update'): result(d,b,state,{},lambda _:True,{'dividends':[old]})


def test_superseding_pending_correction_retains_proof_and_later_resolves(full):
    b,state,d,old=original(full)
    correction=d.model_copy(update={'record_id':'pending','supersedes':d.record_id,'revision_kind':'ENTITLEMENT_BASIS'})
    moved=b.model_copy(deep=True);moved.opening.timestamp=datetime(2026,10,10,tzinfo=timezone.utc)
    pending=result(correction,moved,state,{},lambda _:True,{'dividends':[old]})
    updated=correction.model_copy(update={'record_id':'pending.next','supersedes':'pending','revision_kind':None})
    row=result(updated,moved,state,{},lambda _:True,{'dividends':[pending]})
    assert row['status']=='CORRECTION_PENDING' and row['previous_verified_result']==old
    bank=next(p for p in b.opening.positions if p.ticker==d.ticker);bank.quantity+=50;bank.cost+=5000
    bank=next(p for p in b.closing.positions if p.ticker==d.ticker);bank.quantity+=50;bank.cost+=5000
    recovered=result(updated,b,calculate(b),{},lambda _:True,{'dividends':[row]})
    assert Decimal(recovered['eligible_quantity'])==150
    assert recovered['status']=='PARTIALLY_RECEIVED' and recovered['previous_verified_result'] is None


def test_unverified_changed_evidence_without_explicit_kind_needs_review(full):
    b,state,d,old=original(full)
    next(p for p in b.opening.positions if p.ticker==d.ticker).quantity+=50
    updated=d.model_copy(update={'record_id':'changed','supersedes':d.record_id})
    row=result(updated,b,state,{},lambda _:False,{'dividends':[old]})
    assert row['status']=='CORRECTION_PENDING' and row['previous_verified_result']==old
