"""Exact public allowlist for the standalone W2 extraction scaffold."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=[
 'platform/fde_product/models.py','platform/fde_product/interview_extraction.py','tools/w02_interviews.py',
 'templates/w02_extraction/extraction.json','templates/w02_extraction/extraction_prompt.txt',
 'docs/w02_extraction/README.md','docs/w02_extraction/requirements.txt',
 'examples/w02_extraction/extraction.json','examples/w02_extraction/front_desk.json','examples/w02_extraction/manager.json',
 'tests/test_w02_extraction.py','tools/build_w02_extraction.py',
 *[f'contracts/w02/{name}.schema.json' for name in ('transcript','interview_facts','run_evidence')],
]


def build(root,output):
    root,output=Path(root).resolve(),Path(output)
    data={}
    for name in FILES:
        p=root/name
        if p.is_symlink() or not p.resolve().is_relative_to(root): raise ValueError('SOURCE_PATH_INVALID')
        data[name]=p.read_bytes()
    data['README.md']=b'# W2 interview extraction scaffold\n\nStart with [the Chinese guide](docs/w02_extraction/README.md).\n'
    manifest={'version':'w02-extractor-0.1.0','audience':'learner-candidate','files':{k:hashlib.sha256(v).hexdigest() for k,v in data.items()}}
    data['MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,value in sorted(data.items()):
            info=zipfile.ZipInfo('w02-extractor/'+name,date_time=(2026,9,16,0,0,0));info.external_attr=0o644<<16
            archive.writestr(info,value,compress_type=zipfile.ZIP_DEFLATED)
    return {'path':str(output),'entries':len(data),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(ROOT,p.parse_args().output)))
