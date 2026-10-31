"""Versioned reference adapter registry; replacements require explicit approval."""

from decimal import Decimal

from .runtime import assessment_date

ZERO = Decimal(0)
REGISTRY = {
    'Bank': {'methods': {'BANK_JUSTIFIED_PB'}, 'drivers': {'treasury_gains','credit_costs','oci','capital','dividend_capacity'}},
    'E&P': {'methods': {'FCFE_DCF'}, 'drivers': {'reserves','production','realized_prices','collections','depletion','capex','tax','payout'}},
    'Industrial': {'methods': {'FCFE_DCF','NORMALIZED_MULTIPLE'}, 'drivers': {'operating_drivers','midcycle_margins','capex','working_capital','net_debt'}},
    'OMC': {'methods': {'FCFE_DCF'}, 'drivers': {'volumes','regulated_margins','inventory_effects','working_capital_finance','circular_debt','tax'}},
    'Refining': {'methods': {'FCFE_DCF'}, 'drivers': {'throughput','refining_margins','inventory_effects','working_capital_finance','upgrade_capex','tax'}},
    'IPP': {'methods': {'FINITE_LIFE_FCFE'}, 'drivers': {'contract_life','collections','capacity_payments','debt','guarantees','tax'}},
    'Holding': {'methods': {'SOTP'}, 'drivers': {'component_values','parent_debt','minority_interests','guarantees','capital_allocation'}},
    'Auto': {'methods': {'FCFE_DCF','NORMALIZED_MULTIPLE'}, 'drivers': {'volumes','pricing','localization','fx_costs','capex','working_capital'}},
    'Cement': {'methods': {'FCFE_DCF','NORMALIZED_MULTIPLE'}, 'drivers': {'dispatches','retention_price','fuel_power','utilization','capex','net_debt'}},
    'Textile': {'methods': {'FCFE_DCF','NORMALIZED_MULTIPLE'}, 'drivers': {'volumes','cotton','energy','fx','working_capital','capex'}},
    'Chemical': {'methods': {'FCFE_DCF','NORMALIZED_MULTIPLE'}, 'drivers': {'volumes','product_spreads','feedstock','energy','capex','working_capital'}},
    'Pharma': {'methods': {'FCFE_DCF','NORMALIZED_MULTIPLE'}, 'drivers': {'volumes','regulated_prices','import_costs','fx','working_capital','capex'}},
    'Consumer': {'methods': {'FCFE_DCF','NORMALIZED_MULTIPLE'}, 'drivers': {'volumes','pricing','input_costs','margins','working_capital','capex'}},
    'Insurance': {'methods': {'ROE_BOOK'}, 'drivers': {'underwriting','reserve_quality','investment_income','solvency','payout'}},
    'Shipping': {'methods': {'FCFE_DCF'}, 'drivers': {'freight_rates','routes','fleet','utilization','renewal_capex','debt'}},
}
VERSION = 'sector-reference-v2'


def bridge(forecast, model, bundle):
    fact = next((f for f in bundle.financials if f.record_id == forecast.revenue_fact_id), None)
    sources = {s.source_id:s for s in bundle.sources}
    if (fact is None or fact.ticker != model.ticker or fact.units != 'PKR' or fact.line_item != 'REVENUE'
            or fact.accounting_basis != model.accounting_basis or fact.valid_until < assessment_date(bundle)
            or fact.amount < 0 or not all(s in sources and sources[s].evidence_label=='CONFIRMED' for s in fact.source_ids)):
        raise ValueError('operating bridge requires current confirmed same-basis revenue fact')
    revenue = fact.amount * (1+forecast.revenue_growth)
    ebitda = revenue * forecast.ebitda_margin
    pretax = ebitda - forecast.depreciation - forecast.net_interest_expense + forecast.other_income
    pat = pretax - forecast.tax_charge
    fcfe = pat + forecast.depreciation - forecast.capex - forecast.working_capital_increase + forecast.net_borrowing
    return {'period':forecast.period,'revenue_fact_id':fact.record_id,'revenue':revenue,'ebitda':ebitda,
            'pretax':pretax,'tax_charge':forecast.tax_charge,'pat':pat,'eps':pat/forecast.shares,'fcfe':fcfe,
            'shares':forecast.shares,'source_ids':fact.source_ids,'method':VERSION}


def reference_value(model, scenario, sector, bundle=None):
    adapter = REGISTRY.get(sector)
    if not adapter or model.method not in adapter['methods']:
        raise ValueError('unsupported sector/method: '+sector+'/'+model.method)
    missing = adapter['drivers'] - scenario.drivers.keys()
    if missing or any(not v.strip() for v in scenario.drivers.values()):
        raise ValueError('missing sector driver evidence: '+', '.join(sorted(missing)))
    replacement = sector not in {'Bank','E&P','Industrial'} or model.method not in {'BANK_JUSTIFIED_PB','FCFE_DCF'}
    if replacement:
        approval = model.approval
        sources = {s.source_id:s for s in bundle.sources} if bundle else {}
        if (not approval or approval.model_version != model.model_version or approval.approved_date > model.effective_date
                or not all(s in sources and sources[s].evidence_label=='CONFIRMED' and sources[s].effective_date<=approval.approved_date for s in approval.source_ids)):
            raise ValueError('replacement methodology provisional until version-matched sourced approval')
    s = scenario
    bridges = [bridge(f,model,bundle) for f in s.operating_forecasts] if bundle else []
    if bridges:
        if bridges[0]['period'] != model.forward_period or abs(bridges[0]['eps']-s.forward_eps) > Decimal('0.000001'):
            raise ValueError('forward EPS does not reconcile to numerical operating bridge')
        if s.shares is not None and any(b['shares'] != s.shares for b in bridges):
            raise ValueError('operating bridge and valuation share basis mismatch')
        if s.fcfe and (len(s.fcfe)!=len(bridges) or any(abs(a-b['fcfe'])>Decimal('0.000001') for a,b in zip(s.fcfe,bridges))):
            raise ValueError('FCFE does not reconcile to numerical operating bridge')
        if s.surplus_cash_per_share and any(f.cash_income_included for f in s.operating_forecasts):
            raise ValueError('cash income and surplus cash would be counted twice')
    if model.method in {'BANK_JUSTIFIED_PB','ROE_BOOK'}:
        if s.book_value_per_share is None or s.sustainable_roe is None:
            raise ValueError('ROE/book model needs book value and sustainable ROE')
        value = s.book_value_per_share*(s.sustainable_roe-s.terminal_growth)/(s.discount_rate-s.terminal_growth)
    elif model.method in {'FCFE_DCF','FINITE_LIFE_FCFE'}:
        flows = [b['fcfe'] for b in bridges] if bridges else s.fcfe
        if not flows or s.shares is None or s.terminal_value is None:
            raise ValueError('FCFE model needs cash flows, shares and explicit terminal equity value')
        if model.method == 'FINITE_LIFE_FCFE' and (s.contract_years != len(flows) or s.terminal_value != 0):
            raise ValueError('finite-life valuation requires complete contract life and zero residual perpetuity')
        if sector=='E&P' and s.payout_crosscheck is None:
            raise ValueError('E&P requires a payout cross-check')
        value = (sum((cf/(1+s.discount_rate)**year for year,cf in enumerate(flows,1)),ZERO)
                 + s.terminal_value/(1+s.discount_rate)**len(flows))/s.shares
    elif model.method == 'SOTP':
        if not s.components or s.shares is None or any(v is None for v in (s.parent_net_debt,s.parent_liabilities,s.minority_interests)):
            raise ValueError('SOTP requires explicit component equity values and parent-only liabilities')
        if len({c.component_id for c in s.components}) != len(s.components):
            raise ValueError('duplicate SOTP component')
        sources = {src.source_id:src for src in bundle.sources} if bundle else {}
        if any(any(src not in sources or sources[src].evidence_label!='CONFIRMED' for src in c.source_ids) for c in s.components):
            raise ValueError('unverified SOTP component')
        value = (sum((c.equity_value*c.ownership for c in s.components),ZERO)-s.parent_net_debt-s.parent_liabilities-s.minority_interests)/s.shares
    else:
        if s.normalized_operating_eps is None or s.normalized_operating_eps<=0 or s.earnings_multiple is None:
            raise ValueError('multiple model needs positive normalized operating EPS and an explicit multiple')
        value = s.normalized_operating_eps*s.earnings_multiple
    if s.surplus_cash_per_share:
        if model.method=='SOTP' and s.parent_net_debt is not None and s.parent_net_debt<0:
            raise ValueError('parent net cash already included; separate surplus cash would double count it')
        if s.cash_income_excluded is not True:
            raise ValueError('separate surplus cash requires explicit exclusion of its income from operating valuation')
        value += s.surplus_cash_per_share
    if value<=0:
        raise ValueError('non-positive equity value; no entry level or ranking')
    if s.crosscheck_tolerance is not None:
        if s.payout_crosscheck is None or abs(value-s.payout_crosscheck)/value>s.crosscheck_tolerance:
            raise ValueError('valuation/payout cross-check outside disclosed tolerance')
    return value
