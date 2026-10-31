"""Deterministic monthly wealth projections and explicitly based cross-asset comparisons."""

from calendar import monthrange
from datetime import date
from decimal import Decimal, localcontext
from itertools import combinations
import time

from .record_history import accept_records
from .runtime import assessment_date, cached, BudgetExceeded, json_values, current
from .timing import correlation

ZERO, ONE = Decimal(0), Decimal(1)
SHEETS = {'Wealth_Assets':'assets','Wealth_Flows':'flows','Retirement':'retirement',
          'Retirement_Summary':'projections','Cross_Asset':'cross_asset','Asset_Correlations':'correlations'}
GROUPS = ('assets','flows','scenarios','plans','histories')


def month_at(start, offset):
    ordinal = start.year*12+start.month-1+offset
    year,month = divmod(ordinal,12)
    return date(year,month+1,1)


def project(plan, scenario, assets, flows, balances):
    policies = {r.asset_key:r for r in scenario.returns}
    current_balances = dict(balances)
    rows, first_gap, cumulative_gap = [], None, ZERO
    inflation = ONE
    monthly_inflation = (ONE+scenario.annual_inflation)**(ONE/12)
    policies_monthly = {k:((ONE+p.annual_nominal_return)**(ONE/12)-ONE,
                           ONE-(ONE-p.annual_fee_rate)**(ONE/12)) for k,p in policies.items()}
    for step in range(1,plan.months+1):
        ctx = current()
        if ctx and ctx.max_seconds is not None and time.monotonic()-ctx.began>=ctx.max_seconds:
            ctx.defer('retirement', plan.record_id+'.'+scenario.name)
            raise BudgetExceeded('BUDGET_EXHAUSTED: retirement '+plan.record_id)
        month = month_at(plan.start_date,step-1)
        end = date(month.year,month.month,monthrange(month.year,month.month)[1])
        inflation *= monthly_inflation
        growth_total = fees_total = tax_total = inflows_total = unfunded_charges = ZERO
        for key,balance in list(current_balances.items()):
            policy = policies[key]
            growth_rate,fee_rate = policies_monthly[key]
            gain = balance*growth_rate
            fee = (balance+gain)*fee_rate
            tax = max(ZERO,gain)*policy.return_tax_rate
            unfunded_charges += max(ZERO,-(balance+gain-fee-tax))
            current_balances[key] = max(ZERO,balance+gain-fee-tax)
            growth_total += gain
            fees_total += fee
            tax_total += tax
        spending = plan.monthly_spending_real*inflation if month>=plan.retirement_date else ZERO
        for flow in flows:
            if (flow.starts.year,flow.starts.month) <= (month.year,month.month) <= (flow.ends.year,flow.ends.month):
                amount = flow.amount*inflation if flow.price_basis=='REAL_AT_START' else flow.amount
                if flow.kind=='EXPENSE':
                    spending += amount
                else:
                    current_balances[flow.asset_key] += amount
                    inflows_total += amount
        remaining,withdrawn = spending,ZERO
        for key in plan.withdrawal_order:
            if assets[key].available_from>end:
                continue
            policy = policies[key]
            gross = min(current_balances[key],remaining/(ONE-policy.withdrawal_tax_rate))
            net = gross*(ONE-policy.withdrawal_tax_rate)
            tax_total += gross-net
            current_balances[key] -= gross
            remaining = max(ZERO,remaining-net)
            withdrawn += net
        remaining += unfunded_charges
        if remaining>0 and first_gap is None:
            first_gap = end.isoformat()
        cumulative_gap += remaining
        total = sum(current_balances.values(),ZERO)
        accessible = sum((v for key,v in current_balances.items() if assets[key].available_from<=end),ZERO)
        rows.append({'plan_id':plan.record_id,'scenario':scenario.name,'month':step,'month_end':end.isoformat(),
            'nominal_balance':total,'real_balance':total/inflation,'accessible_balance':accessible,
            'locked_balance':total-accessible,'growth':growth_total,'fees':fees_total,'taxes':tax_total,
            'net_inflows':inflows_total,'net_spending_required':spending,'net_withdrawn':withdrawn,
            'unfunded_charges':unfunded_charges,'funding_gap':remaining,'cumulative_funding_gap':cumulative_gap,'inflation_index':inflation,
            'asset_balances':dict(current_balances)})
    return {'rows':rows,'summary':{'plan_id':plan.record_id,'scenario':scenario.name,'months':plan.months,
            'starting_wealth_pkr':sum(balances.values(),ZERO),'retirement_date':plan.retirement_date.isoformat(),
            'monthly_spending_real':plan.monthly_spending_real,'annual_inflation':scenario.annual_inflation,
            'ending_accessible_balance':rows[-1]['accessible_balance'],'ending_locked_balance':rows[-1]['locked_balance'],
            'ending_nominal_balance':rows[-1]['nominal_balance'],'ending_real_balance':rows[-1]['real_balance'],
            'first_depletion_date':first_gap,'cumulative_funding_gap':cumulative_gap,
            'status':'FUNDED' if first_gap is None else 'FUNDING_SHORTFALL',
            'flow_timing':'MONTH_END_AFTER_RETURNS','return_basis':'SUPPLIED_TOTAL_NOMINAL_PKR',
            'borrowing_assumed':False}}


def calculate_wealth(bundle,state,previous,run_id,input_hash):
    data = bundle.wealth
    if data is None:
        if previous.get('wealth',{}).get('input'):
            raise ValueError('accepted wealth cannot be omitted')
        return
    with localcontext() as context:
        context.prec=48
        return _calculate(bundle,state,previous,run_id,input_hash)


def _calculate(bundle,state,previous,run_id,input_hash):
    data=bundle.wealth
    as_of=assessment_date(bundle)
    sources={s.source_id:s for s in bundle.sources}
    history=accept_records({g:getattr(data,g) for g in GROUPS},previous.get('wealth',{}),bundle,run_id,input_hash)
    provenance={r['record_id']:r for r in history}
    output={'input':data.model_dump(mode='json'),'history':history,**{k:[] for k in SHEETS.values()}}
    gaps=[]
    def good(r):
        return r.effective_date<=as_of<=r.valid_until and all(sources[s].evidence_label=='CONFIRMED' for s in r.source_ids)
    def gap(key,reason):
        row={'ticker':key,'field':'wealth','reason':reason,'owner':'wealth','next_action':'Import dated balances, return/tax assumptions or missing history'}
        gaps.append(row);state['data_gaps'].append(row)
    def meta(r):
        return {'schema_version':'4.0','record_id':r.record_id,'ticker':r.ticker,'owner':'wealth','run_id':run_id,
                'effective_date':r.effective_date.isoformat(),'market_cutoff':bundle.market_cutoff.isoformat(),
                'evaluation_as_of':as_of.isoformat(),'source_ids':r.source_ids,'assumption_ids':[],
                'upstream_run_ids':[provenance[r.record_id]['run_id']],'input_hash':input_hash,
                'confidence':'SYNTHETIC' if bundle.mode=='DEMO' else 'SOURCE_DECLARED',
                'freshness':'CURRENT' if good(r) else 'STALE_OR_UNVERIFIED','validation_status':'VALIDATED' if good(r) else 'BLOCKED',
                'units':'PKR / fraction as named','model_version':'wealth-monthly-v1'}
    assets={a.ticker:a for a in data.assets}
    balances={}
    assets_good=True
    for a in data.assets:
        value=a.balance
        verified=good(a)
        if a.portfolio_link:
            field={'TOTAL':'total_assets','EQUITY':'equity_value','CASH':'cash'}[a.portfolio_link]
            raw=state['summary'].get(field)
            value=Decimal(raw) if raw is not None else None
            verified=verified and not state['reconciliation'] and (as_of-bundle.closing.timestamp.date()).days<=bundle.policy.holdings_max_age_days
            verified=verified and all(sources[s].evidence_label=='CONFIRMED' for s in {bundle.opening.source_id,bundle.closing.source_id}|{p.source_id for p in bundle.prices}|{t.source_id for t in bundle.transactions})
            if a.portfolio_link!='CASH':
                verified=verified and all(h['freshness']=='CURRENT' for h in state['holdings'])
        if a.currency=='USD':
            verified=verified and a.fx_to_pkr is not None and a.fx_date is not None and a.fx_source_id in sources
            verified=verified and bool(a.fx_date and 0<=(as_of-a.fx_date).days<=bundle.policy.price_max_age_days)
            verified=verified and bool(a.fx_source_id in sources and sources[a.fx_source_id].evidence_label=='CONFIRMED')
            value=value*a.fx_to_pkr if value is not None and a.fx_to_pkr is not None else None
        if value is None or not verified:
            assets_good=False;gap(a.ticker,'UNKNOWN_STALE_OR_UNVERIFIED_WEALTH_ASSET')
        else:
            balances[a.ticker]=value
        output['assets'].append({**meta(a),**a.model_dump(mode='json'),'balance_pkr':value,
                                 'spendable_now':value if verified and a.available_from<=as_of else None if not verified else ZERO,
                                 'balance_status':'VERIFIED' if verified and value is not None else 'BLOCKED'})
    for flow in data.flows:
        output['flows'].append({**meta(flow),**flow.model_dump(mode='json')})
    flows_good=all(good(f) and f.amount is not None for f in data.flows)
    retirement_good=bool(data.plans and {s.name for s in data.scenarios}=={'bear','base','bull'} and assets_good and flows_good)
    if not flows_good:
        gap(None,'UNKNOWN_STALE_OR_UNVERIFIED_WEALTH_FLOW')
    complete_count=0
    for plan in data.plans:
        for scenario in data.scenarios:
            rates={r.asset_key:r for r in scenario.returns}
            valid=(assets_good and flows_good and good(plan) and good(scenario) and plan.monthly_spending_real is not None
                   and scenario.annual_inflation is not None and rates.keys()==assets.keys()
                   and all(all(getattr(r,k) is not None for k in ('annual_nominal_return','annual_fee_rate','return_tax_rate','withdrawal_tax_rate')) for r in rates.values()))
            if not valid:
                retirement_good=False
                gap(plan.ticker,'MISSING_RETIREMENT_INPUTS')
                output['projections'].append({**meta(plan),'scenario':scenario.name,'status':'BLOCKED_INPUT',
                                               'ending_nominal_balance':None,'ending_real_balance':None,'first_depletion_date':None})
                continue
            try:
                result=cached('retirement',plan.record_id+'.'+scenario.name,
                    {'plan':plan,'scenario':scenario,'assets':data.assets,'flows':data.flows,'balances':balances,'as_of':as_of},
                    lambda: project(plan,scenario,assets,data.flows,balances))
            except BudgetExceeded:
                ctx=current()
                if ctx: ctx.defer('retirement',plan.record_id+'.'+scenario.name)
                retirement_good=False;gap(plan.ticker,'BUDGET_EXHAUSTED')
                output['projections'].append({**meta(plan),'scenario':scenario.name,'status':'DEFERRED_BUDGET','ending_nominal_balance':None,'ending_real_balance':None})
                continue
            shared={**meta(plan),'assumption_ids':[scenario.record_id],
                    'source_ids':sorted({s for r in [plan,scenario,*data.assets,*data.flows] for s in r.source_ids}),
                    'upstream_run_ids':sorted({provenance[r.record_id]['run_id'] for r in [plan,scenario,*data.assets,*data.flows]})}
            output['retirement'].extend({**shared,**row} for row in result['rows'])
            output['projections'].append({**shared,**result['summary']})
            complete_count+=1
    if not data.plans or {s.name for s in data.scenarios}!={'bear','base','bull'}:
        gap(None,'MISSING_RETIREMENT_PLAN_OR_SCENARIOS')
    histories={}
    cross_good=bool(len(data.histories)>=2)
    if not cross_good:
        gap(None,'INSUFFICIENT_CROSS_ASSET_HISTORIES')
    for h in data.histories:
        valid=good(h)
        converted=[]
        if h.currency=='USD' and (h.fx_source_id not in sources or sources[h.fx_source_id].evidence_label!='CONFIRMED'):
            valid=False
        for quote in h.quotes:
            value=quote.close
            if h.currency=='USD':
                value=value*quote.fx_to_pkr if value is not None and quote.fx_to_pkr is not None else None
            elif quote.fx_to_pkr not in (None,ONE):
                raise ValueError('PKR history has non-unit FX conversion')
            converted.append((quote.session_date,value))
            valid=valid and value is not None and quote.session_date<=bundle.market_cutoff
        if not valid:
            cross_good=False;gap(h.asset_key,'BLOCKED_CROSS_ASSET_HISTORY')
        else:
            histories[h.asset_key]=(h,dict(converted))
        output['cross_asset'].append({**meta(h),'asset_key':h.asset_key,'currency':'PKR','return_basis':h.return_basis,
            'observations':len(converted),'history_start':converted[0][0].isoformat(),'history_end':converted[-1][0].isoformat(),
            'holding_period_return':converted[-1][1]/converted[0][1]-ONE if valid else None,
            'status':'CALCULATED' if valid else 'BLOCKED_HISTORY','allocation_status':'COMPARISON_ONLY_NO_POSITION_CHANGE'})
    for left,right in combinations(sorted(histories),2):
        lh,a=histories[left];rh,b=histories[right]
        try:
            result=cached('cross-asset', left+'.'+right,
                {'left':lh,'right':rh,'minimum':data.min_correlation_observations},
                lambda: compare_histories(lh,a,rh,b,data.min_correlation_observations))
        except BudgetExceeded:
            cross_good=False
            gap(left+' / '+right,'BUDGET_EXHAUSTED')
            result={'correlation':None,'observations':None,'status':'DEFERRED_BUDGET',
                    'common_start':None,'common_end':None,'left_common_return':None,'right_common_return':None}
        if result['status'] not in {'CALCULATED','UNDEFINED_ZERO_VARIANCE'}:
            cross_good=False
        output['correlations'].append({**meta(lh),'left':left,'right':right,**result,
            'source_ids':sorted(set(lh.source_ids+rh.source_ids+([lh.fx_source_id] if lh.fx_source_id else [])+([rh.fx_source_id] if rh.fx_source_id else [])))})
    if not cross_good and data.histories:
        gap(None,'INCOMPLETE_CROSS_ASSET_COMPARISON')
    total=sum(balances.values(),ZERO) if assets_good else None
    output['summary']={'retirement_status':'COMPLETE' if retirement_good and complete_count==len(data.plans)*3 else 'PARTIAL',
        'cross_asset_status':'COMPLETE' if cross_good else 'PARTIAL','total_wealth_pkr':str(total) if total is not None else None,
        'portfolio_totals_treatment':'Referenced once; external assets remain outside PSX holdings',
        'wealth_scope':'DECLARED_ASSETS_ONLY','portfolio_included':any(a.portfolio_link for a in data.assets),
        'mode':bundle.mode,'projection_method':'DETERMINISTIC_MONTHLY','crypto_enabled':data.include_crypto}
    output=json_values(output)
    for key in SHEETS.values():
        old_rows=previous.get('wealth',{}).get(key,[])
        identity=lambda r: tuple(r.get(k) for k in ('record_id','scenario','month','left','right'))
        old_index={identity(r):r for r in old_rows}
        for index,row in enumerate(output[key]):
            old=old_index.get(identity(row))
            ignored={'run_id','input_hash','upstream_run_ids'}
            if old and {k:v for k,v in old.items() if k not in ignored}=={k:v for k,v in row.items() if k not in ignored}:
                output[key][index]=old
    state['wealth']=output


def compare_histories(lh, left, rh, right, minimum):
    common=sorted(left.keys() & right.keys())
    basis_ok=lh.return_basis==rh.return_basis
    x=[left[t]/left[s]-ONE for s,t in zip(common,common[1:])]
    y=[right[t]/right[s]-ONE for s,t in zip(common,common[1:])]
    value=correlation(x,y,minimum) if basis_ok else None
    return {'correlation':value,'observations':len(x),
        'return_basis':lh.return_basis if basis_ok else 'INCOMPATIBLE_BASES',
        'common_start':common[0].isoformat() if common else None,
        'common_end':common[-1].isoformat() if common else None,
        'left_common_return':left[common[-1]]/left[common[0]]-ONE if basis_ok and len(common)>=2 else None,
        'right_common_return':right[common[-1]]/right[common[0]]-ONE if basis_ok and len(common)>=2 else None,
        'status':'CALCULATED' if value is not None else 'UNDEFINED_ZERO_VARIANCE' if basis_ok and len(x)>=minimum else 'INSUFFICIENT_HISTORY_OR_BASIS_MISMATCH'}
