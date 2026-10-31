"""Historical entitlement is an immutable fact, independent of later ledger windows."""
from decimal import Decimal
from .runtime import assessment_date, json_values
from .storage import digest,dumps
ZERO=Decimal(0)


def result(d,bundle,state,metadata,evidence_ok,previous=None):
    previous=previous or {}
    prior={r['record_id']:r for r in previous.get('dividends',[])}
    old=prior.get(d.record_id,{})
    basis=old.get('entitlement_basis')
    correction=prior.get(d.supersedes) or old.get('previous_verified_result')
    pending_correction=old.get('status')=='CORRECTION_PENDING' or bool(correction and correction.get('status')=='CORRECTION_PENDING')
    # A pending correction may itself be superseded; retain the last verified proof.
    while correction and not correction.get('entitlement_basis') and correction.get('previous_verified_result'):
        correction=correction['previous_verified_result']
    receipts=[t for t in state['transactions'] if t['transaction_id'] in d.receipt_transaction_ids]
    if len(receipts)!=len(d.receipt_transaction_ids) or any(t['kind']!='DIVIDEND' or t['ticker']!=d.ticker for t in receipts):
        raise ValueError('receipt must reference an accepted DIVIDEND transaction for the same ticker')
    verified=(evidence_ok(d.source_ids) and d.valid_until>=assessment_date(bundle) and d.dates_verified and
              d.ex_date is not None and d.record_date is not None and d.settlement_rule=='SETTLED_BEFORE_EX')
    window=bool(d.ex_date and bundle.opening.timestamp.date()<d.ex_date<=bundle.closing.timestamp.date())
    used=[]
    if window:
        transactions=sorted({t.transaction_id:t for t in bundle.transactions}.values(),key=lambda t:(t.timestamp,t.transaction_id))
        used=[t.model_dump(mode='json') for t in transactions if t.ticker==d.ticker and
              t.kind in {'BUY','SELL','SPLIT'} and t.settlement_date<d.ex_date]
    opening=bundle.opening.model_dump(mode='json')
    old_basis=correction.get('entitlement_basis') if correction else None
    same_terms=bool(old_basis and str(d.ex_date)==old_basis['ex_date'] and
                    str(d.record_date)==old_basis['record_date'] and Decimal(old_basis['dps'])==d.dps)
    same_evidence=bool(old_basis and opening==old_basis['opening_snapshot'] and used==[
        t for t in old_basis['supporting_transactions'] if t['kind'] in {'BUY','SELL','SPLIT'}])
    if d.revision_kind=='RECEIPT_UPDATE' and old_basis and (not same_terms or window and not same_evidence):
        raise ValueError('receipt update cannot revise entitlement terms or historical evidence')
    if basis is None and verified and window and not state['reconciliation'] and evidence_ok(
            [bundle.opening.source_id,bundle.closing.source_id]+[t.source_id for t in bundle.transactions]):
        if same_terms and same_evidence:
            basis=old_basis
        else:
            quantity=next((p.quantity for p in bundle.opening.positions if p.ticker==d.ticker),ZERO)
            for t in used:
                if t['kind']=='BUY': quantity+=Decimal(t['quantity'])
                elif t['kind']=='SELL': quantity-=Decimal(t['quantity'])
                elif t['kind']=='SPLIT': quantity*=Decimal(t['ratio'])
            if quantity<0: raise ValueError('negative historical dividend entitlement')
            basis={'dividend_id':d.record_id,'ticker':d.ticker,'ex_date':str(d.ex_date),'record_date':str(d.record_date),
                   'dps':str(d.dps),'eligible_quantity':str(quantity),'opening_snapshot':opening,
                   'supporting_transactions':used,'source_ids':sorted(set(d.source_ids+[bundle.opening.source_id]+[t['source_id'] for t in used])),
                   'run_id':metadata.get('run_id'),'calculation_version':'entitlement-v3'}
            basis['basis_id']='entitlement.'+digest(dumps(basis))
    # An ordinary later receipt can carry verified proof beyond its ledger window.
    # Explicit basis corrections and unresolved corrections must never take this shortcut.
    if (basis is None and same_terms and d.revision_kind!='ENTITLEMENT_BASIS'
            and not pending_correction and (not window or same_evidence)
            and evidence_ok(d.source_ids)):
        basis=old_basis
    quantity=Decimal(basis['eligible_quantity']) if basis else None
    gross=quantity*d.dps if quantity is not None else None
    net=gross*(1-d.tax_rate) if gross is not None and d.tax_rate is not None else None
    received=sum((Decimal(t['amount']) for t in receipts),ZERO) if receipts else None
    withheld=sum((Decimal(t['taxes']) for t in receipts),ZERO) if receipts else None
    fees=sum((Decimal(t['fees']) for t in receipts),ZERO) if receipts else None
    pending=max(ZERO,gross-(received or ZERO)) if gross is not None else None
    exception=bool(gross is not None and receipts and (received>gross or d.tax_rate is not None and withheld!=received*d.tax_rate))
    status='PENDING_CONFIRMATION'
    overdue=bool(pending and d.payment_date and d.payment_date<assessment_date(bundle))
    if basis:
        status='NOT_ENTITLED' if quantity==0 else 'OVERDUE' if overdue else 'RECEIVABLE' if d.payment_date else 'ENTITLED'
        if receipts: status='RECEIPT_EXCEPTION' if exception or d.tax_rate is None else 'RECEIVED' if pending==0 else 'PARTIALLY_RECEIVED'
    if basis is None and correction: status='CORRECTION_PENDING'
    row={**metadata,**d.model_dump(mode='json'),'status':status,'eligible_quantity':quantity,'gross_entitlement':gross,
         'net_entitlement':net,'gross_received':received,'net_received':received-withheld-fees if receipts else None,
         'gross_pending':pending,'net_pending':pending*(1-d.tax_rate) if pending is not None and d.tax_rate is not None and not exception else None,
         'overdue':overdue,'entitlement_basis':basis,'tax_status':'UNKNOWN' if d.tax_rate is None else 'EXCEPTION' if exception else 'DECLARED_POLICY',
         'previous_verified_result':correction if status=='CORRECTION_PENDING' else None,
         'cash_treatment':'Receipt already included in portfolio cash; never added again'}
    if row.get('revision_kind') is None: row.pop('revision_kind',None)
    if status in {'PENDING_CONFIRMATION','RECEIPT_EXCEPTION','CORRECTION_PENDING'} or d.tax_rate is None:
        state['data_gaps'].append({'ticker':d.ticker,'field':'dividend','reason':status if d.tax_rate is not None else 'UNKNOWN_DIVIDEND_TAX',
            'owner':'dividends','next_action':'Verify historical basis, correction, withholding and receipts'})
    return json_values(row)
