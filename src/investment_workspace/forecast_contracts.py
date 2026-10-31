"""Closed numerical dimensions and annual period contracts for typed forecasts."""
import re

MONEY = {
    'Bank': frozenset({'tax_charge','fees','treasury_income','operating_costs','credit_charge',
        'opening_equity','oci','capital_movements','opening_eligible_capital','eligible_oci',
        'risk_weighted_assets','distributable_reserves','cash_available','proposed_dividends'}),
    'E&P': frozenset({'tax_charge','royalties','fixed_operating_costs','depletion','net_interest',
        'other_income','opening_receivables','collections','other_working_capital_increase','capex','net_borrowing'}),
    'Industrial': frozenset({'tax_charge','fixed_operating_costs','depreciation','net_interest','other_income',
        'receivables_increase','inventory_increase','payables_increase','capex','net_borrowing'}),
}


def binding_dimension(f, path):
    """Return (canonical unit, physical price denominator); reject non-driver paths."""
    if path == 'shares': return 'SHARES', None
    if path in MONEY[f.engine]: return 'PKR', None
    if f.engine == 'Bank' and path == 'minimum_capital_ratio': return 'FRACTION', None
    match = re.fullmatch(r'(earning_assets|funding|commodities|products)\.(0|[1-9][0-9]*)\.([a-z_]+)', path)
    if match:
        group, index, leaf = match.groups()
        allowed = {'Bank': {'earning_assets','funding'}, 'E&P': {'commodities'}, 'Industrial': {'products'}}
        if group in allowed[f.engine]:
            rows = getattr(f, group)
            if int(index) >= len(rows): raise ValueError('forecast binding index out of range: '+path)
            row = rows[int(index)]
            if group in {'earning_assets','funding'}:
                if leaf == 'average_balance': return 'PKR', None
                if leaf == 'annual_rate': return 'FRACTION', None
            elif group == 'commodities':
                if leaf in {'opening_reserves','reserve_additions','production','inventory_release','sold'}:
                    return row.unit, None
                if leaf == 'realized_price': return row.price_currency+'_PER_UNIT', row.unit
                if leaf == 'operating_cost_per_unit_pkr': return 'PKR_PER_UNIT', row.unit
                if leaf == 'fx_to_pkr': return ('PKR_PER_USD' if row.price_currency == 'USD' else 'FRACTION'), None
            elif group == 'products':
                if leaf == 'volume': return row.unit, None
                if leaf in {'net_price_pkr','variable_cost_per_unit_pkr'}: return 'PKR_PER_UNIT', row.unit
    raise ValueError('unsupported numerical forecast binding: '+path)


def validate_periods(model, forecasts):
    """Annual lists must start at the model's forward period and be contiguous.

    The model's investment holding horizon is independent of the DCF projection
    length. Terminal discounting uses the validated annual projection length.
    """
    if not forecasts: return
    if forecasts[0].period != model.forward_period:
        raise ValueError('forecast period does not match valuation forward period')
    if model.forward_basis == 'NTM':
        if model.forward_period != 'NTM' or len(forecasts) != 1:
            raise ValueError('NTM supports one annual forecast; multi-year NTM requires explicit dated mapping')
        return
    def parse(label):
        match = re.fullmatch(r'(FY|CY)([0-9]{2}|[1-9][0-9]{3})', label)
        if not match or match[1] != model.forward_basis:
            raise ValueError('unsupported or conflicting annual forecast period: '+label)
        return int(match[2]), len(match[2])
    start, width = parse(model.forward_period)
    for offset, forecast in enumerate(forecasts):
        year, digits = parse(forecast.period)
        if digits != width or year != start + offset:
            raise ValueError('annual forecast periods must be ordered and contiguous on one year basis')
