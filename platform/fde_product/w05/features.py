"""Recent purchase evidence on imported W03 order semantics, with coverage states."""
from datetime import date,timedelta
from .contracts import PurchaseFeatureRequest

def recent_purchase(connection,dataset,request):
    r=PurchaseFeatureRequest.model_validate(request)
    coverage=[date.fromisoformat(x) for x in dataset['coverage']]
    ref=r.reference_date;start=ref-timedelta(days=r.dormant_days)
    version={k:dataset.get(k) for k in ['id','grain_version','identity_rule_version','library_sha256']}
    if not connection.execute('select 1 from raw_members where member_id=?',[r.member_id]).fetchone():
        return {'status':'not_found','member_id':r.member_id,'versions':version}
    if coverage[0]>start or coverage[1]<ref:
        return {'status':'unknown','code':'DORMANCY_WINDOW_NOT_COVERED','member_id':r.member_id,'is_dormant':None,'coverage':dataset['coverage'],'versions':version}
    # Half-open ref and strict positive net payment. Cancellation and full
    # refunds are excluded; refund-over-payment was quarantined during import.
    last=connection.execute("select max(ordered_at) from raw_orders where member_id=? and ordered_at<? and status='paid' and paid_cents>refund_cents",[r.member_id,ref]).fetchone()[0]
    if last is None:
        return {'status':'unknown','code':'NO_EFFECTIVE_PURCHASE_IN_EXPORT','member_id':r.member_id,'is_dormant':None,'coverage':dataset['coverage'],'versions':version}
    age=(ref-last).days
    return {'status':'ok','member_id':r.member_id,'last_effective_purchase':str(last),'dormant_days':age,'is_dormant':age>=r.dormant_days,'reference_date':str(ref),'versions':version}
