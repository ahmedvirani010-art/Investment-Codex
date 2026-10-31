import json, tempfile, os
from copy import deepcopy
from pathlib import Path
from decimal import Decimal
from datetime import date
from investment_workspace import pipeline
from investment_workspace.schemas import Bundle,FinancialFact
from investment_workspace.models import reference_value
from investment_workspace.sector_engines import forecast
from investment_workspace.storage import dumps,digest,read_json,git,head,committed
from investment_workspace.workspace_requests import execute
import investment_workspace.object_storage as storage

full=json.loads(pipeline.fixture_bytes(completion=True))
out={}
# Evidence unit for a realized commodity price contradicts the declared price.
b=Bundle.model_validate(full);m=b.research.models[1];s=m.scenarios[0];f=s.sector_forecasts[0]
base=next(x for x in b.financials if x.record_id in f.fact_ids)
bad=base.model_copy(update={'record_id':'audit.price-unit','line_item':'REALIZED_PRICE','amount':f.commodities[0].realized_price,'units':'SHARES'})
b.financials.append(bad);f.fact_ids.append(bad.record_id);f.fact_bindings['commodities.0.realized_price']=bad.record_id
# Revalidate the whole public contract, rather than relying on model_copy bypasses.
b=Bundle.model_validate(b.model_dump(mode='json'));m=b.research.models[1];s=m.scenarios[0]
try:
 value=reference_value(m,s,'E&P',b)
 out['incompatible_price_fact_unit']={'expected':'BLOCKED','observed':'ACCEPTED','fact_unit':'SHARES','bound_field':'commodities.0.realized_price','valuation':str(value)}
except ValueError as e:out['incompatible_price_fact_unit']={'observed':'BLOCKED','error':str(e)}
# Changing the second cash-flow period must not leave its discount timing unchanged.
vals={}
for period in ('FY28','FY37'):
 b=Bundle.model_validate(full);m=b.research.models[1];s=m.scenarios[0]
 second=s.sector_forecasts[0].model_copy(deep=True);second.period=period;s.sector_forecasts.append(second)
 s.fcfe=[forecast(f,m,b)['fcfe'] for f in s.sector_forecasts]
 # Keep this test about time basis, not an intentionally tight payout threshold.
 s.crosscheck_tolerance=Decimal('.99')
 b=Bundle.model_validate(b.model_dump(mode='json'));m=b.research.models[1];s=m.scenarios[0]
 try:vals[period]={'observed':'ACCEPTED','valuation':str(reference_value(m,s,'E&P',b))}
 except ValueError as e:vals[period]={'observed':'BLOCKED','error':str(e)}
out['noncontiguous_cashflow_period']=vals
# Missing R2 object: check persisted request and transfer receipts without network.
class Missing(Exception): response={'Error':{'Code':'NoSuchKey'}}
class Fake:
 def get_object(self,**kw):raise Missing()
os.environ['R2_BUCKET']='synthetic-audit-bucket'
storage.time.sleep=lambda _:None
with tempfile.TemporaryDirectory(prefix='plan-audit-') as folder:
 root=Path(folder)/'workspace';r=pipeline.run(root,dumps(full));assert r['status']!='FAILED',r
 policy=json.loads(Path('config/storage.json').read_bytes());policy['enabled']=True
 (root/'config').mkdir(exist_ok=True);(root/'config/storage.json').write_bytes(dumps(policy));git(root,'add','config/storage.json');git(root,'-c','user.name=Audit','-c','user.email=audit@localhost','commit','-qm','Synthetic policy')
 state=read_json(root,pipeline.STATE)
 req={'request_id':'audit.failed-pull','operation':'storage.pull','dataset_id':state['dataset']['dataset_id'],'expected_run_id':state['published_run_id'],
 'as_of':'2026-10-09','authorized_by':'Synthetic audit','instruction':'Probe inaccessible synthetic R2 object',
 'storage':{'request_id':'audit.failed-pull','operation':'pull','objects':[{'key':'approved/missing.json','sha256':'0'*64}]}}
 path=root/'requests/workspace/audit.failed-pull.json';path.parent.mkdir(parents=True);path.write_bytes(dumps(req))
 git(root,'add',str(path.relative_to(root)));git(root,'-c','user.name=Audit','-c','user.email=audit@localhost','commit','-qm','Synthetic request')
 result=execute(root,path,local_demo=True,s3=Fake())
 out['failed_workspace_transfer']={'status':result['status'],'errors':result.get('errors'),'transfer_status':result.get('transfer'),'durable_storage_receipt':read_json(root,'reports/storage/audit.failed-pull.json')}
 # Published metadata on the new shared profiles.
 rows=read_json(root,pipeline.STATE)['shared_scenarios']['rows']
 fields=('code_version','code_hash','model_version','source_ids','assumption_ids','upstream_run_ids')
 out['shared_profile_metadata']={'missing':[k for k in fields if k not in rows[0]],'profile_id':rows[0]['record_id']}
Path('/tmp/prd-plan-gap-probe.json').write_bytes(dumps(out));print(json.dumps(out,indent=2))
