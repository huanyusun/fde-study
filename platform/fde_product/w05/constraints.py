"""Structured, sourceful policy evidence. Unknown wording is never permission."""
from typing import Literal
from pydantic import Field,StrictInt
from .contracts import Contract,IdentityResult

class Restriction(Contract):
    source_id: str
    scope: Literal['all','telephone','sms','unknown']
    source_file: str=Field(min_length=1)
    source_row: StrictInt=Field(ge=1)
    quote: str=Field(min_length=1)
    rule_version: str=Field(min_length=1)

class Exclusion(Contract):
    source_id: str
    kind: Literal['employee','abnormal_identity']
    verification: Literal['confirmed','suspected','unknown']
    source_file: str=Field(min_length=1)
    source_row: StrictInt=Field(ge=1)
    quote: str=Field(min_length=1)
    rule_version: str=Field(min_length=1)

def member_constraints(member_id,mapping,restrictions,exclusions=()):
    mapped=[IdentityResult.model_validate(x) for x in mapping]
    ids={x.source_id for x in mapped if x.member_id==member_id and x.status in ['resolved','singleton']}
    if not ids:return {'status':'not_found','member_id':member_id}
    records=[Restriction.model_validate(x) for x in restrictions]
    evidence=[r.model_dump() for r in records if r.source_id in ids]
    excluded=[Exclusion.model_validate(x) for x in exclusions if x['source_id'] in ids]
    scopes={r['scope'] for r in evidence};confirmed=[x.model_dump() for x in excluded if x.verification=='confirmed']
    pending=[x.model_dump() for x in excluded if x.verification!='confirmed']
    channels={c:'blocked' if 'all' in scopes or c in scopes else 'unknown' if 'unknown' in scopes else 'no_known_restriction' for c in ['telephone','sms']}
    # Absence of a recorded restriction does not authorize actual contact.
    return {'status':'unknown' if pending or 'unknown' in scopes else 'ok','member_id':member_id,
        'channels':channels,'excluded_from_recommendation':bool(confirmed),'confirmed_exclusions':confirmed,
        'pending_verifications':pending,'restriction_evidence':evidence,'actual_contact_authorized':False}

def registration_scope(store_id,mapping,relationships):
    """Only evidence-linked registration stores qualify; global unknowns aren't repeated lists."""
    lookup={x['source_id']:IdentityResult.model_validate(x) for x in mapping};stores={}
    for x in lookup.values():
        if x.member_id:stores.setdefault(x.member_id,set())
    for record in relationships:
        r=lookup.get(record['source_id'])
        if r and r.member_id and record.get('registered_store'):
            # Transaction-store data must never be supplied under this field.
            if record.get('relation')!='source_account_registered_store' or not record.get('source_file') or type(record.get('source_row')) is not int:raise ValueError('REGISTRATION_RELATION_PROVENANCE_REQUIRED')
            stores[r.member_id].add(record['registered_store'])
    eligible=sorted(mid for mid,s in stores.items() if store_id is None or store_id in s)
    return {'member_ids':eligible,'range_notice':{'no_known_registration_member_count':sum(not s for s in stores.values()),
        'identity_unresolved_source_account_count':sum(not r.member_id for r in lookup.values()),
        'scope':'all_verified_members' if store_id is None else 'members_with_evidenced_source_account_registration_at_store',
        'unknown_relationships_are_not_confirmed_nonmembership':True,'global_unknowns_are_not_per_store_pending_lists':True}}
