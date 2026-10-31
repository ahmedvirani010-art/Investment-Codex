"""Phase 2: reject wrong dimensions and incorrect discount-period mappings."""
import json
from copy import deepcopy
from decimal import Decimal
from datetime import date
from pathlib import Path

import pytest
from investment_workspace import pipeline
from investment_workspace.schemas import Bundle,FinancialFact
from investment_workspace.models import reference_value
from investment_workspace.sector_engines import forecast
from investment_workspace.storage import dumps,read_json

RAW=json.loads(pipeline.fixture_bytes(completion=True))


def numerical_paths(value,prefix=''):
    if isinstance(value,Decimal): yield prefix
    elif isinstance(value,dict):
        for key,item in value.items(): yield from numerical_paths(item,prefix+'.'+key if prefix else key)
    elif isinstance(value,list):
        for index,item in enumerate(value): yield from numerical_paths(item,prefix+'.'+str(index))


def setup(index=1):
    b=Bundle.model_validate(deepcopy(RAW));m=b.research.models[index];s=m.scenarios[0]
    return b,m,s,s.sector_forecasts[0]


def bind(b,m,f,path,unit,quantity=None):
    value=f.model_dump()
    for part in path.split('.'): value=value[int(part)] if isinstance(value,list) else value[part]
    base=next(x for x in b.financials if x.record_id in f.fact_ids)
    data=base.model_dump(mode='json');data.update(record_id='test.binding',line_item='SUPPLIED_DRIVER',amount=str(value),units=unit,quantity_unit=quantity)
    fact=FinancialFact.model_validate(data);b.financials.append(fact)
    f.fact_bindings[path]=fact.record_id;f.fact_ids=list(dict.fromkeys(f.fact_bindings.values()))
    return fact


ALL_DRIVERS=[(i,path) for i in range(3) for path in numerical_paths(setup(i)[3].model_dump())]


@pytest.mark.parametrize('index,path',ALL_DRIVERS)
def test_every_numeric_driver_rejects_incompatible_currency(index,path):
    b,m,s,f=setup(index);bind(b,m,f,path,'USD')
    with pytest.raises(ValueError,match='units/currency/quantity'): forecast(f,m,b)


@pytest.mark.parametrize('index,path,unit,quantity',[
 (0,'earning_assets.0.average_balance','PKR',None),(0,'funding.0.annual_rate','FRACTION',None),
 (0,'minimum_capital_ratio','FRACTION',None),(0,'shares','SHARES',None),(0,'oci','PKR',None),
 (1,'commodities.0.realized_price','PKR_PER_UNIT','BBL'),(1,'commodities.0.sold','BBL',None),
 (1,'commodities.0.operating_cost_per_unit_pkr','PKR_PER_UNIT','BBL'),(1,'commodities.0.fx_to_pkr','FRACTION',None),
 (1,'other_working_capital_increase','PKR',None),(2,'products.0.volume','UNITS',None),
 (2,'products.0.net_price_pkr','PKR_PER_UNIT','UNITS'),(2,'products.0.variable_cost_per_unit_pkr','PKR_PER_UNIT','UNITS'),
 (2,'net_borrowing','PKR',None)])
def test_canonical_bindings_preserve_hand_calculated_pat(index,path,unit,quantity):
    b,m,s,f=setup(index);bind(b,m,f,path,unit,quantity)
    b=Bundle.model_validate(b.model_dump(mode='json'));m=b.research.models[index];f=m.scenarios[0].sector_forecasts[0]
    assert forecast(f,m,b)['pat']==[Decimal(50),Decimal(100),Decimal(70)][index]


@pytest.mark.parametrize('quantity',[None,'MCF','TONNES'])
def test_price_denominator_must_match_sold_volume(quantity):
    b,m,s,f=setup();bind(b,m,f,'commodities.0.realized_price','PKR_PER_UNIT',quantity)
    with pytest.raises(ValueError,match='quantity'): reference_value(m,s,'E&P',b)


def test_explicit_usd_fx_preserves_eps_and_fcfe():
    b,m,s,f=setup();c=f.commodities[0]
    c.price_currency='USD';c.realized_price/=2;c.fx_to_pkr=Decimal(2)
    bind(b,m,f,'commodities.0.realized_price','USD_PER_UNIT','BBL')
    # Give the FX binding a separate immutable fact ID.
    price=b.financials[-1];price.record_id='test.price';f.fact_ids[-1]=price.record_id;f.fact_bindings['commodities.0.realized_price']=price.record_id
    fx=bind(b,m,f,'commodities.0.fx_to_pkr','PKR_PER_USD')
    row=forecast(f,m,b)
    assert row['pat']==100 and row['eps']==10 and row['fcfe']==75
    assert reference_value(m,s,'E&P',b)>0
    fx.units='FRACTION'
    with pytest.raises(ValueError,match='currency'): forecast(f,m,b)


@pytest.mark.parametrize('path',['period','engine','cash_income_included','fact_ids.0','commodities.0.unit','commodities.0.name',
    'commodities.0.__class__','commodities.01.sold','commodities.99.sold','shares.extra'])
def test_non_driver_and_out_of_range_bindings_are_blocked(path):
    b,m,s,f=setup();f.fact_bindings[path]=f.fact_ids[0]
    with pytest.raises(ValueError,match='binding'): forecast(f,m,b)


def test_future_evidence_is_not_current():
    b,m,s,f=setup();base=next(x for x in b.financials if x.record_id in f.fact_ids)
    base.effective_date=date(2026,10,10)
    with pytest.raises(ValueError,match='current confirmed'): forecast(f,m,b)


def two_periods(first='FY27',second='FY28',basis='FY'):
    b,m,s,f=setup();m.forward_period=first;m.forward_basis=basis;f.period=first
    following=f.model_copy(deep=True);following.period=second;s.sector_forecasts.append(following)
    s.fcfe=[Decimal(75),Decimal(75)];s.crosscheck_tolerance=Decimal('.99')
    return b,m,s


@pytest.mark.parametrize('first,second,basis',[('FY27','FY37','FY'),('FY27','FY26','FY'),('FY27','CY28','FY'),
 ('FY27','FY2028','FY'),('FY2027','FY28','FY'),('FY99','FY00','FY'),('FY27','unknown','FY'),('FY27','FY28','CY')])
def test_gapped_reordered_and_conflicting_periods_are_blocked(first,second,basis):
    b,m,s=two_periods(first,second,basis)
    with pytest.raises(ValueError,match='period'): reference_value(m,s,'E&P',b)


@pytest.mark.parametrize('first,second,basis',[('FY27','FY28','FY'),('FY2027','FY2028','FY'),
 ('CY2027','CY2028','CY'),('FY2099','FY2100','FY')])
def test_contiguous_annual_flows_match_independent_discounting(first,second,basis):
    b,m,s=two_periods(first,second,basis)
    # This is a two-year DCF projection, distinct from the investment holding horizon.
    expected=(Decimal(75)/(1+s.discount_rate)+Decimal(75)/(1+s.discount_rate)**2+s.terminal_value/(1+s.discount_rate)**2)/s.shares
    assert reference_value(m,s,'E&P',b)==expected


def test_share_basis_mismatch_still_blocks_valid_periods():
    b,m,s=two_periods();s.sector_forecasts[1].shares+=1
    with pytest.raises(ValueError,match='share basis'): reference_value(m,s,'E&P',b)


def test_ntm_supports_one_explicit_annual_period_only():
    b,m,s,f=setup();m.forward_basis='NTM';m.forward_period='NTM';f.period='NTM'
    assert reference_value(m,s,'E&P',b)>0
    s.sector_forecasts.append(f.model_copy(update={'period':'NTM+1'}))
    with pytest.raises(ValueError,match='NTM'): reference_value(m,s,'E&P',b)


def test_wrong_unit_blocks_pipeline_certification(repo):
    b,m,s,f=setup();bind(b,m,f,'commodities.0.realized_price','SHARES')
    result=pipeline.run(repo,dumps(b.model_dump(mode='json')));assert result['status']!='FAILED',result
    state=read_json(repo,pipeline.STATE)
    assert state['research']['summary']['valuation_status']!='COMPLETE'
    assert any(g['ticker']==m.ticker and 'units/currency/quantity' in g.get('reason','') for g in state['coverage'])
