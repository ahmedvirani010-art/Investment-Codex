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
    correction=prior.get(d.supersedes) if d.supersedes else None
    if basis is None and correction and evidence_ok(d.source_ids) and correction.get('entitlement_basis'):
        old_basis=correction['entitlement_basis']
        if str(d.ex_date)==old_basis['ex_date'] and str(d.record_date)==old_basis['record_date'] and str(d.dps)==old_basis['dps']:
            basis=old_basis
    receipts=[t for t in state['transactions'] if t['transaction_id'] in d.receipt_transaction_ids]
    if len(receipts)!=len(d.receipt_transaction_ids) or any(t['kind']!='DIVIDEND' or t['ticker']!=d.ticker for t in receipts):
        raise ValueError('receipt must reference an accepted DIVIDEND transaction for the same ticker')
    verified=(evidence_ok(d.source_ids) and d.valid_until>=assessment_date(bundle) and d.dates_verified and
              d.ex_date is not None and d.record_date is not None and d.settlement_rule=='SETTLED_BEFORE_EX')
    window=bool(d.ex_date and bundle.opening.timestamp.date()<d.ex_date<=bundle.closing.timestamp.date())
    if basis is None and verified and window and not state['reconciliation'] and evidence_ok(
            [bundle.opening.source_id,bundle.closing.source_id]+[t.source_id for t in bundle.transactions]):
        quantity=next((p.quantity for p in bundle.opening.positions if p.ticker==d.ticker),ZERO)
        transactions=sorted({t.transaction_id:t for t in bundle.transactions}.values(),key=lambda t:(t.timestamp,t.transaction_id))
        used=[]
        for t in transactions:
            if t.ticker!=d.ticker or t.settlement_date>=d.ex_date: continue
            if t.kind=='BUY': quantity+=t.quantity
            elif t.kind=='SELL': quantity-=t.quantity
            elif t.kind=='SPLIT': quantity*=t.ratio
            used.append(t.model_dump(mode='json'))
        if quantity<0: raise ValueError('negative historical dividend entitlement')
        basis={'dividend_id':d.record_id,'ticker':d.ticker,'ex_date':str(d.ex_date),'record_date':str(d.record_date),
               'dps':str(d.dps),'eligible_quantity':str(quantity),'opening_snapshot':bundle.opening.model_dump(mode='json'),
               'supporting_transactions':used,'source_ids':sorted(set(d.source_ids+[bundle.opening.source_id]+[t['source_id'] for t in used])),
               'run_id':metadata.get('run_id'),'calculation_version':'entitlement-v2'}
        basis['basis_id']='entitlement.'+digest(dumps(basis))
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
    correction=prior.get(d.supersedes) if d.supersedes else None
    if basis is None and correction: status='CORRECTION_PENDING'
    row={**metadata,**d.model_dump(mode='json'),'status':status,'eligible_quantity':quantity,'gross_entitlement':gross,
         'net_entitlement':net,'gross_received':received,'net_received':received-withheld-fees if receipts else None,
         'gross_pending':pending,'net_pending':pending*(1-d.tax_rate) if pending is not None and d.tax_rate is not None and not exception else None,
         'overdue':overdue,'entitlement_basis':basis,'tax_status':'UNKNOWN' if d.tax_rate is None else 'EXCEPTION' if exception else 'DECLARED_POLICY',
         'previous_verified_result':correction if status=='CORRECTION_PENDING' else None,
         'cash_treatment':'Receipt already included in portfolio cash; never added again'}
    if status in {'PENDING_CONFIRMATION','RECEIPT_EXCEPTION','CORRECTION_PENDING'} or d.tax_rate is None:
        state['data_gaps'].append({'ticker':d.ticker,'field':'dividend','reason':status if d.tax_rate is not None else 'UNKNOWN_DIVIDEND_TAX',
            'owner':'dividends','next_action':'Verify historical basis, correction, withholding and receipts'})
    return json_values(row)
