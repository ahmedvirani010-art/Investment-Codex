"""Shared identity/evidence checks for new owned input collections."""

from copy import deepcopy
from .contracts import normalize


def accept_records(groups, previous, bundle, run_id, input_hash):
    history = deepcopy(previous.get('history', []))
    known = {r['record_id']: r for r in history}
    active = {r['record_id']: (name, r) for name, group in previous.get('input', {}).items()
              if isinstance(group, list) for r in group if isinstance(r, dict) and 'record_id' in r}
    sources = {s.source_id for s in bundle.sources}
    incoming, superseded = set(), set()
    for group, records in groups.items():
        for record in records:
            if record.record_id in incoming:
                raise ValueError('duplicate owned record ID')
            incoming.add(record.record_id)
            if not set(record.source_ids) <= sources or record.effective_date > bundle.market_cutoff:
                raise ValueError('unregistered source or post-cutoff owned record')
            payload = record.model_dump(mode='json')
            old = known.get(record.record_id)
            if old:
                if normalize(old['payload']) != normalize(payload) or record.record_id not in active:
                    raise ValueError('owned record ID immutable; use explicit supersession')
                continue
            if record.supersedes:
                prior = active.get(record.supersedes)
                if (not prior or prior[0] != group or prior[1]['ticker'] != record.ticker or
                        record.effective_date.isoformat() < prior[1]['effective_date'] or record.supersedes in superseded):
                    raise ValueError('invalid owned record supersession')
                superseded.add(record.supersedes)
            history.append({'record_id': record.record_id, 'group': group, 'payload': payload,
                            'run_id': run_id, 'input_hash': input_hash})
    if set(active) - incoming - superseded:
        raise ValueError('accepted owned record omitted without supersession')
    return history
