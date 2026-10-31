"""Versioned shared assumptions with explicit, checked domain mappings."""
from decimal import Decimal
from .record_history import accept_records
from .runtime import assessment_date,json_values


def value_at(record,path):
    value=record.model_dump() if hasattr(record,'model_dump') else record
    for part in path.split('.'):
        if part.startswith('_'): raise ValueError('invalid assumption binding')
        value=value[int(part)] if isinstance(value,list) and part.isdigit() else value[part]
    return Decimal(str(value))


def prepare(bundle,state,previous,run_id,input_hash):
    history=accept_records({'profiles':bundle.scenario_profiles},previous.get('shared_scenarios',{}),bundle,run_id,input_hash)
    if bundle.scenario_profiles or history:
        state['shared_scenarios']={'input':{'profiles':[p.model_dump(mode='json') for p in bundle.scenario_profiles]},'history':history,'rows':[{**p.model_dump(mode='json'),'owner':'shared_scenarios','run_id':next(h['run_id'] for h in history if h['record_id']==p.record_id)} for p in bundle.scenario_profiles]}


def resolve(bundle,scenario,*,basis=None,period=None,horizon=None):
    link=scenario.profile
    if link is None:
        if bundle.mode=='USER_IMPORT': raise ValueError('shared scenario mapping required for current real-data certification')
        return {'status':'LEGACY_REFERENCE','profile_id':None,'effective_assumptions':{}}
    profile=next((p for p in bundle.scenario_profiles if p.record_id==link.profile_id),None)
    sources={s.source_id:s for s in bundle.sources}
    def confirmed(ids):
        return bool(ids) and all(i in sources and sources[i].evidence_label=='CONFIRMED' for i in ids)
    if profile is None or profile.name!=scenario.name or not profile.effective_date<=assessment_date(bundle)<=profile.valid_until or not confirmed(profile.source_ids):
        raise ValueError('missing, stale, unverified or mismatched shared scenario profile')
    differs=(link.financial_basis!=profile.financial_basis or link.period!=profile.period or link.horizon_years!=profile.horizon_years)
    if differs and (not link.mapping_rationale or not confirmed(link.source_ids)):
        raise ValueError('domain scenario differences require a sourced explicit mapping')
    if basis is not None and link.financial_basis!=basis or period is not None and link.period!=period or horizon is not None and link.horizon_years!=horizon:
        raise ValueError('scenario mapping differs from actual model basis, period or horizon')
    assumptions=dict(profile.assumptions)
    for key,override in link.overrides.items():
        if key not in assumptions or override.assumption.unit!=assumptions[key].unit or not confirmed(override.source_ids):
            raise ValueError('scenario override requires matching units and confirmed evidence')
        assumptions[key]=override.assumption
    if not link.bindings or set(link.bindings)!=set(link.binding_units) or not set(link.overrides)<=set(link.bindings):
        raise ValueError('scenario mappings require explicit bindings and units; overrides must be consumed')
    for key,path in link.bindings.items():
        assumption=assumptions.get(key)
        leaf=path.split('.')[-1]
        expected_unit='FRACTION' if leaf in {'discount_rate','terminal_growth','annual_inflation','revenue_growth','annual_nominal_return','annual_fee_rate','return_tax_rate','withdrawal_tax_rate','sustainable_roe'} else 'PKR_PER_SHARE' if leaf in {'forward_eps','sustainable_dps','exit_price','book_value_per_share'} else None
        if assumption is None or assumption.value is None or link.binding_units[key]!=assumption.unit or expected_unit and assumption.unit!=expected_unit:
            raise ValueError('scenario binding unit mismatch')
        try: amount=value_at(scenario,path)
        except (KeyError,IndexError,TypeError,ValueError,ArithmeticError) as exc: raise ValueError('invalid numerical scenario binding: '+path) from exc
        if amount!=assumption.value: raise ValueError('owned forecast differs from shared assumption; explicit override/revision required: '+key)
    return json_values({'status':'LINKED','profile_id':profile.record_id,'profile_version':profile.profile_version,
                       'effective_assumptions':assumptions,'bindings':link.bindings,'overrides':link.overrides,
                       'source_ids':sorted(set(profile.source_ids+link.source_ids+[s for o in link.overrides.values() for s in o.source_ids]))})
