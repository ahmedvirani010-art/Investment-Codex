import json,tempfile
from copy import deepcopy
from pathlib import Path
from investment_workspace import pipeline
from investment_workspace.storage import dumps,read_json
full=json.loads(pipeline.fixture_bytes(completion=True))
with tempfile.TemporaryDirectory(prefix='div-correction-audit-') as tmp:
 root=Path(tmp)/'workspace';pipeline.run(root,dumps(full));old=read_json(root,pipeline.STATE)['research']['dividends'][0]
 x=deepcopy(full)
 def newsource(source_id,tag):
  s=deepcopy(next(s for s in x['sources'] if s['source_id']==source_id));s['source_id']='synthetic.audit.'+tag;x['sources'].append(s);return s['source_id']
 for name in ('opening','closing'):
  x[name]['source_id']=newsource(x[name]['source_id'],name)
  p=next(p for p in x[name]['positions'] if p['ticker']=='DEMO-BANK');p['quantity']=str(int(p['quantity'])+50);p['cost']=str(int(float(p['cost']))+5000)
 d=x['research']['dividends'][0];d['supersedes']=d['record_id'];d['record_id']='div.bank.corrected-basis';d['source_ids']=[newsource(d['source_ids'][0],'dividend')]
 result=pipeline.run(root,dumps(x))
 out={'result_status':result['status'],'error':result.get('error')}
 if result['status']!='FAILED':
  row=read_json(root,pipeline.STATE)['research']['dividends'][0]
  out.update(original_quantity=old['eligible_quantity'],corrected_opening_quantity=x['opening']['positions'][0]['quantity'],returned_quantity=row['eligible_quantity'],returned_gross=row['gross_entitlement'],same_old_basis=row['entitlement_basis']==old['entitlement_basis'],reconciliation=read_json(root,pipeline.STATE)['reconciliation'])
  # Compare with calculation based on the same corrected evidence and no earlier basis.
  from investment_workspace.schemas import Bundle
  from investment_workspace.portfolio import calculate
  from investment_workspace.dividends import result as dividend
  b=Bundle.model_validate(x);fresh=dividend(b.research.dividends[0],b,calculate(b),{},lambda _:True)
  out['corrected_evidence_quantity']=fresh['eligible_quantity'];out['corrected_evidence_gross']=fresh['gross_entitlement']
 print(json.dumps(out,indent=2));Path('/tmp/prd-dividend-correction-probe.json').write_bytes(dumps(out))
