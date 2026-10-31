"""Equivalent-input, parity-gated synthetic measurements; never touches caller data."""

import json
import tempfile
import time
import platform
from importlib.metadata import version
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from statistics import median

from . import pipeline
from .storage import dumps, digest
from .wealth_requests import sandbox


def benchmark(*, samples=3, months=360):
    if type(samples) is not int or not 1<=samples<=10 or type(months) is not int or not 1<=months<=1200:
        raise ValueError('benchmark requires 1..10 samples and 1..1200 months')
    data=json.loads(pipeline.fixture_bytes(phase4=True))
    data['wealth']['plans'][0]['months']=months
    report={'code_hash':pipeline.code_hash(),'input_hash':digest(dumps(data)),
            'python_version':platform.python_version(),'dependencies':{p:version(p) for p in ('pydantic','openpyxl')},
            'dataset':'SYNTHETIC_ONLY','months':months,'samples':samples,'ai_cost':None,
            'parity':'PASS','measurements':[],'timing_scope':'sandbox clone, calculation, workbook, local commit and parity validation'}
    with tempfile.TemporaryDirectory(prefix='wealth-benchmark-') as temp:
        root=Path(temp)/'baseline'
        pipeline.run(root,dumps(data),workflow='benchmark-seed')
        changed=deepcopy(data)
        scenario=changed['wealth']['scenarios'][0]
        scenario['supersedes']=scenario['record_id']
        scenario['record_id']+='-benchmark'
        source=deepcopy(changed['sources'][-1]);source['source_id']='synthetic.wealth.benchmark-policy'
        changed['sources'].append(source);scenario['source_ids']=[source['source_id']]
        scenario['returns'][0]['annual_nominal_return']=str(Decimal(scenario['returns'][0]['annual_nominal_return'])+Decimal('.01'))
        for case,inputs in (('unchanged',data),('one_assumption_changed',changed)):
            times={'full':[],'cached':[]}
            for sample in range(samples):
                states={}
                for mode in ('full','cached') if sample%2==0 else ('cached','full'):
                    start=time.perf_counter()
                    temporary,work,result,state=sandbox(root,inputs,None,max_units=None,max_seconds=None,recalculate=mode=='full')
                    try:
                        times[mode].append(time.perf_counter()-start)
                        states[mode]=state
                        usage=state['usage'][-1]
                        report['measurements'].append({'case':case,'sample':sample+1,'mode':mode,
                            'seconds':times[mode][-1],'calculation_units':usage['calculation_units'],
                            'cache_hits':usage['cache_hits'],'phase_seconds':usage['phase_runtime_seconds']})
                    finally:
                        temporary.cleanup()
                if not pipeline.same_analytics(states['full'],states['cached']):
                    raise ValueError('benchmark parity failed; runtime comparison invalid')
            full,cached=median(times['full']),median(times['cached'])
            report[case]={'full_median_seconds':full,'cached_median_seconds':cached,
                          'full_over_cached_ratio':full/cached if cached else None}
    return report
