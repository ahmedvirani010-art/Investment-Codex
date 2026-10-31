"""Independent hand values for the replacement model registry and financial bridge."""

import json
from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
from importlib.resources import files

import pytest

from investment_workspace import pipeline
from investment_workspace.models import REGISTRY, reference_value, bridge
from investment_workspace.schemas import Bundle, ValuationModel, FinancialFact, OperatingForecast
from investment_workspace.storage import dumps, read_json


@pytest.fixture
def full_model():
    return json.loads(files('investment_workspace').joinpath('fixtures/phase4-demo.json').read_bytes())


def model_for(full,sector,method):
    model=deepcopy(full['research']['models'][2])
    model.update(method=method,model_version='reference-test-v2',
        approval={'approved_by':'synthetic reviewer','approved_date':'2026-10-09','model_version':'reference-test-v2',
                  'methodology_validated':True,'source_ids':['synthetic.research.v1'],'rationale':'SYNTHETIC arithmetic validation'})
    for s in model['scenarios']:
        s['drivers']={key:'explicit synthetic source rationale' for key in REGISTRY[sector]['drivers']}
        if method=='FINITE_LIFE_FCFE':
            s.update(contract_years=2,terminal_value='0')
        if method=='SOTP':
            s.update(components=[{'component_id':'A','equity_value':'1000','ownership':'1','source_ids':['synthetic.research.v1']},
                                 {'component_id':'B','equity_value':'500','ownership':'0.5','source_ids':['synthetic.research.v1']}],
                     parent_net_debt='100',parent_liabilities='50',minority_interests='25')
        if method=='NORMALIZED_MULTIPLE':
            s.update(normalized_operating_eps='5',earnings_multiple='10',surplus_cash_per_share='2',cash_income_excluded=True)
    return ValuationModel.model_validate(model)


@pytest.mark.parametrize('sector,method',[(s,m) for s,a in REGISTRY.items() for m in sorted(a['methods'])])
def test_each_sector_adapter_against_hand_value(full_model,sector,method):
    bundle=Bundle.model_validate(full_model)
    model=model_for(full_model,sector,method)
    scenario=next(s for s in model.scenarios if s.name=='base')
    with localcontext() as ctx:
        ctx.prec=48
        result=reference_value(model,scenario,sector,bundle)
        if method in {'BANK_JUSTIFIED_PB','ROE_BOOK'}:
            expected=Decimal(225)
        elif method=='SOTP': expected=Decimal('107.5')
        elif method=='NORMALIZED_MULTIPLE': expected=Decimal(52)
        elif method=='FINITE_LIFE_FCFE': expected=(Decimal(100)/Decimal('1.1')+Decimal(110)/Decimal('1.21'))/10
        else: expected=(Decimal(100)/Decimal('1.1')+Decimal(110)/Decimal('1.21')+Decimal(1210)/Decimal('1.21'))/10
        assert abs(result-expected)<Decimal('1e-25')


def test_provisional_replacement_cannot_bypass_approval(full_model):
    bundle=Bundle.model_validate(full_model)
    model=model_for(full_model,'Shipping','FCFE_DCF')
    model.approval=None
    with pytest.raises(ValueError,match='provisional'):
        reference_value(model,model.scenarios[0],'Shipping',bundle)


def test_finite_life_and_surplus_cash_guards(full_model):
    bundle=Bundle.model_validate(full_model)
    model=model_for(full_model,'IPP','FINITE_LIFE_FCFE')
    model.scenarios[0].terminal_value=Decimal(1)
    with pytest.raises(ValueError,match='zero residual'):
        reference_value(model,model.scenarios[0],'IPP',bundle)
    model=model_for(full_model,'Consumer','NORMALIZED_MULTIPLE')
    model.scenarios[0].cash_income_excluded=False
    with pytest.raises(ValueError,match='exclusion'):
        reference_value(model,model.scenarios[0],'Consumer',bundle)


def test_numeric_operating_bridge_reconciles_eps_fcfe_and_sources(full_model,repo):
    fact={'record_id':'revenue.fact.1','ticker':'DEMO-INDUSTRIAL','effective_date':'2026-10-09','valid_until':'2026-10-12',
          'source_ids':['synthetic.research.v1'],'period_start':'2025-07-01','period_end':'2026-06-30',
          'accounting_basis':'STANDALONE','line_item':'REVENUE','amount':'1000','units':'PKR','locator':'synthetic filing p1'}
    full_model['financials']=[fact]
    f={'period':'FY27','revenue_fact_id':'revenue.fact.1','revenue_growth':'0','ebitda_margin':'0.2','depreciation':'10',
       'net_interest_expense':'5','other_income':'0','tax_charge':'25','capex':'30','working_capital_increase':'20',
       'net_borrowing':'0','shares':'10','cash_income_included':False}
    model=full_model['research']['models'][2]
    for s in model['scenarios']:
        s.update(operating_forecasts=[f],fcfe=['120'],forward_eps='16',terminal_value='0')
    bundle=Bundle.model_validate(full_model)
    result=bridge(OperatingForecast.model_validate(f),bundle.research.models[2],bundle)
    assert result['revenue']==1000
    assert result['pretax']==185
    assert result['pat']==160
    assert result['eps']==16
    assert result['fcfe']==120
    published=pipeline.run(repo,dumps(full_model))
    assert published['status']!='FAILED', published.get('error')
    state=read_json(repo,pipeline.STATE)
    forecast=next(r for r in state['research']['forecasts'] if r['ticker']=='DEMO-INDUSTRIAL')
    assert forecast['eps']=='16.0'
    assert forecast['revenue_fact_id']=='revenue.fact.1'
    assert pipeline.validate(repo)['workbook_parity']=='PASS'


def test_eps_and_crosscheck_mismatches_block_reference_value(full_model):
    model=model_for(full_model,'Shipping','FCFE_DCF')
    model.scenarios[0].crosscheck_tolerance=Decimal('0.001')
    model.scenarios[0].payout_crosscheck=Decimal(1)
    with pytest.raises(ValueError,match='cross-check'):
        reference_value(model,model.scenarios[0],'Shipping',Bundle.model_validate(full_model))
