import hashlib
import json

import pytest


def test_local_pack_requires_consent_and_preserves_existing_destination(tmp_path):
    from async_rbench.submissions.github_only.pack import prepare_submission
    target=tmp_path/'output'
    with pytest.raises(ValueError,match='consent'):
        prepare_submission(tmp_path/'runs',tmp_path/'manifest',tmp_path/'audit',{},target,consent=False)
    assert not target.exists()
    target.mkdir(); (target/'keep.txt').write_text('keep')
    with pytest.raises(ValueError,match='new'):
        prepare_submission(tmp_path/'runs',tmp_path/'manifest',tmp_path/'audit',{},target,consent=True)
    assert (target/'keep.txt').read_text()=='keep'


def test_command_packages_originals_and_matching_private_request_without_network(tmp_path, monkeypatch, capsys):
    from private_review_fixtures import full_evidence
    from async_rbench.submissions.github_only.pack import main
    from async_rbench.submissions.private_review.bundle import inspect_bundle
    import socket
    def blocked(*args,**kwargs):raise AssertionError('No network permitted')
    monkeypatch.setattr(socket,'create_connection',blocked)
    runs,manifest,audit,metadata,policy=full_evidence(tmp_path/'originals')
    meta=tmp_path/'metadata.json';meta.write_text(json.dumps(metadata))
    target=tmp_path/'submission'
    assert main(['--runs',str(runs),'--manifest',str(manifest),'--audit',str(audit),'--metadata',str(meta),
                 '--output',str(target),'--consent-summary'])==0
    assert {p.name for p in target.iterdir()}=={'submission.json','evidence.zip'}
    raw=(target/'evidence.zip').read_bytes()
    request=json.loads((target/'submission.json').read_text())
    assert request=={'schema':'async-rbench-private-request-1','evidence_path':'evidence.zip',
                     'evidence_sha256':hashlib.sha256(raw).hexdigest(),'consent':True}
    assert inspect_bundle(raw,tmp_path/'checked',policy)['metrics']['episodes']==600
    output=capsys.readouterr().out
    assert 'PRIVATE_EVIDENCE' not in output and '600' in output
