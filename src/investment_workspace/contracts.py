"""Compatibility normalization: additive absent fields never rewrite old evidence IDs."""

ADDITIONS = {'quantity_unit', 'revision_kind', 'covered_event_ids', 'approval', 'crosscheck_tolerance', 'contract_years', 'components',
             'parent_net_debt', 'parent_liabilities', 'minority_interests', 'normalized_operating_eps',
             'earnings_multiple', 'surplus_cash_per_share', 'cash_income_excluded', 'operating_forecasts',
             'url', 'published_at', 'accessed_at', 'document_sha256', 'coverage_through', 'owner',
             'dataset_id', 'financials', 'migrations', 'wealth', 'documents', 'profile', 'sector_forecasts', 'scenario_profiles', 'decisions'}


def normalize(value):
    if isinstance(value, dict):
        return {k: normalize(v) for k,v in value.items() if not (k in ADDITIONS and (v is None or v == []))}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def payload(record):
    return normalize(record.model_dump(mode='json'))


def active_sources(bundle):
    result=set()
    def visit(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='sources':
                    continue
                if key in {'source_id','fx_source_id'} and isinstance(item,str):
                    result.add(item)
                elif key=='source_ids':
                    result.update(item)
                else:
                    visit(item)
        elif isinstance(value,list):
            for item in value:
                visit(item)
    visit(bundle.model_dump(mode='json'))
    return sorted(result)
