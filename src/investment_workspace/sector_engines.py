"""First-wave numerical reference forecasts; approval is required by valuation."""
from decimal import Decimal
from .runtime import assessment_date
from .scenarios import value_at
Z=Decimal(0)
VERSION='sector-numeric-v1'


def forecast(f,model,bundle):
    def missing(value):
        if value is None: return True
        if isinstance(value,dict): return any(missing(v) for v in value.values())
        if isinstance(value,list): return any(missing(v) for v in value)
        return False
    if missing(f.model_dump()): raise ValueError('missing numerical forecast driver; certification blocked')
    sources={s.source_id:s for s in bundle.sources}
    if f.accounting_basis!=model.accounting_basis or any(s not in sources or sources[s].evidence_label!='CONFIRMED' for s in f.source_ids):
        raise ValueError('forecast basis or evidence mismatch')
    facts={x.record_id:x for x in bundle.financials}
    if set(f.fact_bindings.values())!=set(f.fact_ids): raise ValueError('forecast fact IDs must be bound to numerical inputs')
    for path,record_id in f.fact_bindings.items():
        fact=facts.get(record_id)
        if (fact is None or fact.ticker!=model.ticker or fact.accounting_basis!=model.accounting_basis or fact.valid_until<assessment_date(bundle)
                or any(s not in sources or sources[s].evidence_label!='CONFIRMED' for s in fact.source_ids)):
            raise ValueError('current confirmed financial facts required for sector forecast')
        if value_at(f,path)!=fact.amount: raise ValueError('forecast input does not reconcile to its financial fact')
        leaf=path.split('.')[-1]
        unit='FRACTION' if 'rate' in leaf or leaf.endswith('ratio') else 'SHARES' if leaf=='shares' else None
        if leaf in {'opening_reserves','reserve_additions','production','inventory_release','sold','volume'}:
            parent=f.model_dump()
            for part in path.split('.')[:-1]: parent=parent[int(part)] if isinstance(parent,list) else parent[part]
            unit=parent.get('unit')
        if unit and fact.units!=unit: raise ValueError('financial fact units differ from forecast binding')
        if unit is None and leaf in {'opening_equity','opening_eligible_capital','opening_receivables','capex','fixed_operating_costs'} and fact.units!='PKR':
            raise ValueError('monetary base fact must be PKR')
    rows={'period':f.period,'shares':f.shares,'source_ids':sorted(set(f.source_ids+[s for i in f.fact_ids for s in facts[i].source_ids])),
          'fact_ids':f.fact_ids,'method':VERSION,'engine':f.engine}
    if f.engine=='Bank':
        interest=sum((x.average_balance*x.annual_rate for x in f.earning_assets),Z)
        funding=sum((x.average_balance*x.annual_rate for x in f.funding),Z)
        pretax=interest-funding+f.fees+f.treasury_income-f.operating_costs-f.credit_charge
        pat=pretax-f.tax_charge
        capacity=max(Z,min(f.distributable_reserves,f.cash_available,
                         f.opening_eligible_capital+pat+f.eligible_oci+f.capital_movements-f.risk_weighted_assets*f.minimum_capital_ratio))
        if f.proposed_dividends>capacity: raise ValueError('proposed bank dividend exceeds sourced cash/reserve/capital capacity')
        closing=f.opening_equity+pat+f.oci+f.capital_movements-f.proposed_dividends
        if closing<=0: raise ValueError('bank closing equity must be positive')
        rows.update(interest_income=interest,funding_cost=funding,pretax=pretax,tax_charge=f.tax_charge,pat=pat,eps=pat/f.shares,
                    oci=f.oci,opening_equity=f.opening_equity,closing_equity=closing,
                    sustainable_roe=pat/((f.opening_equity+closing)/2),book_value_per_share=f.opening_equity/f.shares,
                    dividend_capacity=capacity,sustainable_dps=f.proposed_dividends/f.shares)
    else:
        if f.engine=='E&P':
            if len({c.name for c in f.commodities})!=len(f.commodities): raise ValueError('duplicate commodity')
            revenue=cost=Z
            for c in f.commodities:
                if c.production>c.opening_reserves+c.reserve_additions or c.sold>c.production+c.inventory_release:
                    raise ValueError('production/sales exceed reserves or available volumes')
                if c.price_currency=='PKR' and c.fx_to_pkr!=1: raise ValueError('PKR commodity price requires unit FX')
                revenue+=c.sold*c.realized_price*c.fx_to_pkr
                cost+=c.production*c.operating_cost_per_unit_pkr
            if f.collections>f.opening_receivables+revenue: raise ValueError('collections exceed available receivables')
            movement=revenue-f.collections
            depreciation=f.depletion
            ebitda=revenue-cost-f.royalties-f.fixed_operating_costs
            wc=movement+f.other_working_capital_increase
            rows.update(revenue=revenue,receivable_increase=movement,closing_receivables=f.opening_receivables+movement)
        else:
            if len({p.product for p in f.products})!=len(f.products): raise ValueError('duplicate product')
            revenue=sum((p.volume*p.net_price_pkr for p in f.products),Z)
            cost=sum((p.volume*p.variable_cost_per_unit_pkr for p in f.products),Z)
            ebitda=revenue-cost-f.fixed_operating_costs
            depreciation=f.depreciation
            wc=f.receivables_increase+f.inventory_increase-f.payables_increase
            rows.update(revenue=revenue,midcycle_rationale=f.midcycle_rationale)
        pretax=ebitda-depreciation-f.net_interest+f.other_income
        pat=pretax-f.tax_charge
        rows.update(ebitda=ebitda,pretax=pretax,tax_charge=f.tax_charge,pat=pat,eps=pat/f.shares,
                    depreciation=depreciation,working_capital_increase=wc,
                    fcfe=pat+depreciation-f.capex-wc+f.net_borrowing)
    return rows
