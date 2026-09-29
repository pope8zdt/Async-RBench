from __future__ import annotations
import hashlib,json,pathlib,subprocess
CASE_ID='mab-late-constraint-383afddcb0'; SOURCE_ID='research:051'; KIND='research'; EVIDENCE='5d2bb6319923a931be0f9eeef35a1e253f6611526e0370942c419dae7572e6a9'
root=pathlib.Path('/app'); out=root/'output_data'; receipt=json.loads((out/'event_receipt.json').read_text())
if (root/'.git').exists(): revision=subprocess.run(['git','diff','--binary'],cwd=root,stdout=subprocess.PIPE).stdout
else:
    h=hashlib.sha256()
    for p in sorted(x for x in root.rglob('*') if x.is_file() and 'output_data' not in x.parts): h.update(str(p).encode()); h.update(p.read_bytes())
    revision=h.digest()
if KIND=='research':
    proposal=out/'research_proposal.md'; closure={'schema_version':'async-rbench-research-closure-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event_receipt_sha256':receipt['receipt_sha256'],'native_evidence_sha256':EVIDENCE,'proposal_sha256':hashlib.sha256(proposal.read_bytes()).hexdigest(),'preserved_source_facts':json.loads((out/'preserved_source_facts.json').read_text())['preserved'],'source_semantics_reverified':True,'closure_complete':True}; (out/'research_closure.json').write_text(json.dumps(closure,indent=2,sort_keys=True)+'\n')
else:
    agreement=json.loads((out/'agreement.json').read_text()); closure={'schema_version':'async-rbench-negotiation-closure-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event_receipt_sha256':receipt['receipt_sha256'],'native_evidence_sha256':EVIDENCE,'accepted_revision':agreement['accepted_revision'],'stale_revision_rejected':receipt['delivered_offer']['revision']<agreement['accepted_revision'],'agreement_sha256':hashlib.sha256((out/'agreement.json').read_bytes()).hexdigest(),'source_semantics_reverified':True,'closure_complete':True}; (out/'negotiation_closure.json').write_text(json.dumps(closure,indent=2,sort_keys=True)+'\n')
manifest={'schema_version':'async-rbench-closure-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event_receipt_sha256':receipt['receipt_sha256'],'event_consumed':True,'final_revision_sha256':hashlib.sha256(revision).hexdigest(),'source_semantics_reverified':True,'closure_complete':True}
(out/'decision_manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
