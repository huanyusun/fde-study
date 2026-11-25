"""Versioned entity descriptions; preserve all W03 executable dimension IDs."""
from .common import read

def validate_targets(folder,legacy):
    from pathlib import Path
    folder=Path(folder);path=folder/'dimension_targets.json'
    contract_path=folder/'entity_semantics.json'
    if not contract_path.exists() and (not path.exists() or read(path)==legacy):return {'version':'w03-account-1','grain':'source_account'}
    targets=read(path)
    if not contract_path.exists():raise ValueError('DIMENSION_TARGET_CONTRACT_MISMATCH')
    contract=read(contract_path);scope=read(folder/'scope.json')
    expected={'version','grain_version','member','home_store','sources'}
    if contract.get('version')=='w05-entity-semantics-2':expected.add('unresolved_bucket_policy')
    if set(contract)!=expected or contract['version'] not in ['w05-entity-semantics-1','w05-entity-semantics-2']:raise ValueError('ENTITY_SEMANTICS_CONTRACT_INVALID')
    if not contract['grain_version'] or scope.get('grain_version')!=contract['grain_version']:raise ValueError('ENTITY_GRAIN_VERSION_MISMATCH')
    if (contract['member']!=('verified_person_with_unresolved_source_buckets' if contract['version']=='w05-entity-semantics-2' else 'verified_person') or contract['home_store']!='representative_attribute' or (contract['version']=='w05-entity-semantics-2' and contract['unresolved_bucket_policy']!='retain_financial_records_not_verified_people')):raise ValueError('ENTITY_SEMANTICS_UNSUPPORTED')
    if not contract['sources'] or not all(isinstance(s,str) and s.strip() for s in contract['sources']):raise ValueError('ENTITY_SEMANTICS_SOURCES_REQUIRED')
    if not isinstance(targets,list) or len(targets)!=len(legacy):raise ValueError('DIMENSION_TARGET_IDS_CHANGED')
    if [t.get('id') for t in targets]!=[t['id'] for t in legacy]:raise ValueError('DIMENSION_TARGET_IDS_CHANGED')
    for old,new in zip(legacy,targets):
        if set(new)!=set(old) or not all(isinstance(new[k],str) and new[k].strip() for k in new):raise ValueError('DIMENSION_TARGET_METADATA_INVALID')
        if old['id'] not in {'member','home_store','home_store__region','home_store__store_name','member__tier'} and old!=new:raise ValueError('UNRELATED_DIMENSION_MEANING_CHANGED')
        if old['id']=='member' and new['meaning']==old['meaning']:raise ValueError('NATURAL_PERSON_MEANING_REQUIRED')
    return contract
