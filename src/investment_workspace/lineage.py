"""Uniform derived-row code lineage; frozen snapshots are never rewritten."""
from . import __version__
from .runtime import current
from .storage import read_json


def stamp(state,root,run_id):
    ctx=current()
    groups=[state.get(k,[]) for k in ('holdings','transactions','coverage','data_gaps','notes')]
    for module in ('research','integration','wealth','financials','decisions','shared_scenarios'):
        groups += [v for k,v in state.get(module,{}).items() if isinstance(v,list) and k not in {'history','entitlements'}]
    groups.append([state.get('summary',{})])
    for rows in groups:
        for row in rows:
            if not isinstance(row,dict): continue
            origin=row.get('run_id',run_id)
            manifest=read_json(root,'runs/'+origin+'/manifest.json',{}) if origin!=run_id else {}
            row.setdefault('code_version',manifest.get('code_version',__version__))
            row.setdefault('code_hash',manifest.get('code_hash',ctx.code_hash if ctx else None))
