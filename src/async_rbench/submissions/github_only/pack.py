"""Prepare a private submission from existing artifacts; never calls any API."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

from ..artifacts import strict_json, validate_receipt
from ..private_review.bundle import pack_bundle, MAX_ARCHIVE, MAX_EXPANDED, MAX_FILE, PATH


def prepare_submission(runs, manifest, audit, metadata, output, *, consent=False):
    if consent is not True:
        raise ValueError('Explicit public-summary consent is required')
    destination=Path(output)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Submission output must be a new directory')
    destination=destination.resolve()
    project=Path(__file__).resolve().parents[4]
    if destination.is_relative_to(project/'docs'):
        raise ValueError('Keep private evidence outside website sources')
    raw=pack_bundle(runs,manifest,audit,metadata)
    if not 0<len(raw)<=MAX_ARCHIVE:
        raise ValueError('Evidence archive exceeds the private submission limit')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos=archive.infolist()
        if (len(infos)!=1203 or len({i.filename for i in infos})!=1203
                or sum(i.file_size for i in infos)>MAX_EXPANDED
                or any(not PATH.fullmatch(i.filename) or i.file_size>MAX_FILE
                       or i.file_size>max(i.compress_size,1)*250 for i in infos)):
            raise ValueError('Full bounded evidence is required')
        receipt=strict_json(archive.read('receipt.json'))
    result=validate_receipt(receipt)
    if not result['valid'] or result['coverage']!={'tasks':200,'episodes':600,'repetitions':3}:
        raise ValueError('Submit all 200 tasks with three Async repetitions')
    # This checks local integrity, not maintainer policy or acceptance. Only the
    # trusted private worker can approve the judge/corpus/runtime provenance.
    request={'schema':'async-rbench-private-request-1','evidence_path':'evidence.zip',
             'evidence_sha256':hashlib.sha256(raw).hexdigest(),'consent':True}
    destination.mkdir(mode=0o700,parents=True,exist_ok=False)
    for name,data in (('evidence.zip',raw),('submission.json',json.dumps(request,indent=2).encode())):
        path=destination/name
        with path.open('xb') as stream:
            path.chmod(0o600)
            stream.write(data)
    return {'prepared':True,'episodes':600,'remote_writes':0,'accepted':False}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runs','manifest','audit','metadata','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--consent-summary',action='store_true',required=True,
                        help='Consent to publishing only the approved community summary')
    args=parser.parse_args(argv)
    try:
        report=prepare_submission(args.runs,args.manifest,args.audit,strict_json(args.metadata.read_bytes()),
                                  args.output,consent=args.consent_summary)
        print(json.dumps(report))
        return 0
    except (OSError,ValueError,KeyError,TypeError):
        # Never echo raw trace content or potentially sensitive paths/metadata.
        print(json.dumps({'prepared':False,'message':'Check original artifacts, full coverage, consent and a new private output directory.'}))
        return 1


if __name__=='__main__':raise SystemExit(main())
