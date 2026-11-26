"""Customer-approved edges enter ETL. Weak clues never merge automatically."""
import hashlib
from collections import defaultdict
from .contracts import IdentityEvidence, IdentityResult

def resolve(source_ids,evidence,*,mapping_version,verified_singletons=(),previous=None):
    ids=list(source_ids)
    if len(ids)!=len(set(ids)) or any(':' not in x or not all(x.split(':',1)) for x in ids):raise ValueError('NAMESPACED_UNIQUE_SOURCE_IDS_REQUIRED')
    if not mapping_version:raise ValueError('MAPPING_VERSION_REQUIRED')
    parent={s:s for s in ids};proof=defaultdict(set);denied=[];review=set();previous=previous or {}
    def root(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    records=[IdentityEvidence.model_validate(x) for x in evidence]
    if len({r.evidence_id for r in records})!=len(records):raise ValueError('DUPLICATE_EVIDENCE_ID')
    for r in records:
        if r.left not in parent or r.right not in parent:raise ValueError('EVIDENCE_SOURCE_NOT_FOUND')
        if r.left==r.right:raise ValueError('IDENTITY_SELF_EDGE')
        proof[r.left].add(r.evidence_id);proof[r.right].add(r.evidence_id)
        if r.relation=='same':parent[root(r.right)]=root(r.left)
        elif r.relation=='different':denied.append((r.left,r.right))
        else:review.update([r.left,r.right])
    components=defaultdict(list)
    for sid in ids:components[root(sid)].append(sid)
    conflict={root(a) for a,b in denied if root(a)==root(b)}
    singleton=set(verified_singletons)
    if not singleton<=set(ids):raise ValueError('SINGLETON_SOURCE_NOT_FOUND')
    result=[];used={}
    for key,nodes in sorted(components.items()):
        nodes=sorted(nodes);status='conflict' if key in conflict else 'unresolved' if any(s in review for s in nodes) else 'resolved' if len(nodes)>1 else 'singleton' if nodes[0] in singleton else 'unresolved'
        earlier={previous[s] for s in nodes if previous.get(s)}
        # A merge of previously separate identities requires a new reviewed version,
        # rather than silently choosing one previously published member ID.
        if len(earlier)>1:status='conflict'
        member=None
        if status in ['resolved','singleton']:
            member=next(iter(earlier),None) or 'U'+hashlib.sha256(nodes[0].encode()).hexdigest()[:24]
            if member in used and used[member]!=nodes:raise ValueError('PREVIOUS_ID_SPLIT_OR_COLLISION')
            used[member]=nodes
        evidence_ids=sorted(set().union(*(proof[s] for s in nodes)))
        result.extend(IdentityResult(source_id=s,member_id=member,status=status,evidence_ids=evidence_ids,mapping_version=mapping_version).model_dump() for s in nodes)
    return result

def map_records(records,mapping,*,source_field='source_id'):
    """Every input record is accepted or retained for review, without changing amounts."""
    lookup={r['source_id']:IdentityResult.model_validate(r) for r in mapping};accepted=[];quarantined=[]
    if len(lookup)!=len(mapping):raise ValueError('DUPLICATE_MAPPING_SOURCE')
    for number,record in enumerate(records,1):
        item=lookup.get(record[source_field])
        if not item or not item.member_id:
            quarantined.append({'source_record':number,'reason':'IDENTITY_UNRESOLVED' if not item else 'IDENTITY_'+item.status.upper(),'raw':dict(record)})
        else:accepted.append({**record,'member_id':item.member_id,'mapping_version':item.mapping_version})
    assert len(records)==len(accepted)+len(quarantined)
    return {'accepted':accepted,'quarantined':quarantined,'counts':{'read':len(records),'accepted':len(accepted),'quarantined':len(quarantined)}}
