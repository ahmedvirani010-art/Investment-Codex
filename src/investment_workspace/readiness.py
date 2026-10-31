"""Read-only readiness and workflow-specific completeness from committed facts."""

from .storage import read_json
from .migration import active_legacy


def workflow_status(state, workflow):
    if state.get('attempt_status') == 'FAILED':
        return 'FAILED'
    if workflow == 'valuation':
        return state.get('research', {}).get('summary', {}).get('valuation_status', 'BLOCKED_INPUT')
    if workflow == 'update-dividends':
        rows = state.get('research', {}).get('dividends', [])
        return 'COMPLETE' if rows and not any(r['status'] in {'PENDING_CONFIRMATION','RECEIPT_EXCEPTION'} for r in rows) else 'PARTIAL'
    if workflow in {'retirement', 'cross-asset'}:
        return state.get('wealth', {}).get('summary', {}).get('retirement_status' if workflow == 'retirement' else 'cross_asset_status', 'BLOCKED_INPUT')
    if workflow in {'timing','macro','watchlist','ic'}:
        return state.get('integration', {}).get('summary', {}).get(workflow+'_status', 'BLOCKED_INPUT')
    if workflow in {'daily','event','analyze'}:
        return state.get('integration', {}).get('summary', {}).get('integration_status', 'BLOCKED_INPUT')
    return 'COMPLETE' if state.get('summary', {}).get('data_gate_status') == 'PASSED' else 'PARTIAL'


def report(state, *, schedules=None, production=None):
    if not state:
        return {'status': 'BLOCKED_INPUT', 'dependencies': [{'owner':'portfolio','next_action':'Initialize a dataset and import confirmed balances'}]}
    compatibility = 'VERIFIED' if active_legacy(state.get('migration_records',[])) else 'NOT_MIGRATED'
    facts = {k:workflow_status(state,k) for k in ('portfolio','valuation','timing','macro','watchlist','ic','retirement','cross-asset')}
    dependencies = [{'owner':g.get('owner'), 'reason':g['reason'], 'next_action':g.get('next_action'), 'ticker':g.get('ticker')}
                    for g in state.get('data_gaps',[])]
    if compatibility != 'VERIFIED':
        dependencies.append({'owner':'migration','reason':'LEGACY_PARITY_REQUIRED','next_action':'Supply and reconcile the real legacy datastore'})
    roles={d['role'] for d in state.get('documents',[])}
    missing_contracts=sorted({'EVIDENCE_CONTRACT','REPLACEMENT_PROMPTS','VALUATION_RERUN'}-roles)
    for role in missing_contracts:
        dependencies.append({'owner':'evidence','reason':'MISSING_'+role,'next_action':'Import the original PRD source document with hash and locator'})
    declared=[s for s in state.get('sources',[]) if not s['source_id'].startswith(('input.','manual.')) and
              ('active_source_ids' not in state or s['source_id'] in state['active_source_ids'])]
    provenance_complete=bool(declared and all(s.get('accessed_at') and s.get('coverage_through') and s.get('owner') and (s.get('url') or s.get('document_sha256')) for s in declared))
    if not provenance_complete:
        dependencies.append({'owner':'evidence','reason':'INCOMPLETE_PROVENANCE','next_action':'Import publication/access metadata, ownership, coverage dates and source URL or original hash'})
    production = production or {}
    provided_indicators={m['indicator'] for m in state.get('integration',{}).get('macro',[]) if m.get('selected_current',True)}
    missing_indicators=set(production.get('required_macro_indicators',[]))-provided_indicators
    for indicator in sorted(missing_indicators):
        dependencies.append({'owner':'macro_news','reason':'MISSING_REQUIRED_INDICATOR','next_action':'Import '+indicator})
    production_ready = (state.get('dataset',{}).get('mode')=='USER_IMPORT' and compatibility=='VERIFIED'
                        and all(facts[k]=='COMPLETE' for k in ('portfolio','valuation','timing','macro','watchlist','ic'))
                        and state.get('integration',{}).get('summary',{}).get('mean_reversion_status')=='COMPLETE'
                        and provenance_complete and not missing_contracts and not missing_indicators and production.get('enabled') is True and production.get('manual_parity_verified') is True)
    if not production_ready:
        dependencies.append({'owner':'deployment','reason':'NOT_ACTIVATED','next_action':'Confirm production dataset, manual parity, source coverage and publication policy'})
    return {'dataset':state.get('dataset'), 'calculation_status':state.get('attempt_status'),
            'evaluation_as_of':state.get('evaluation_as_of',state['summary'].get('market_cutoff')),
            'coverage':facts, 'compatibility':compatibility,
            'deployment':'READY' if production_ready else 'BLOCKED',
            'schedules_enabled':bool(schedules and schedules.get('enabled')),
            'dependencies':dependencies}


def committed_report(root):
    return report(read_json(root,'data/canonical/portfolio.json'), schedules=read_json(root,'config/schedules.json'),
                  production=read_json(root,'config/production.json'))
