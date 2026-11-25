"""Controlled filters on original MetricFlow SQL; stable full-result paging."""
import hashlib,json
from pathlib import Path
from .contracts import AggregateFilter,Page

def aggregate_query(project,intent,filters=(),page=None,_all=False):
    from ..metrics.engine import Engine,READ_ONLY
    import duckdb
    engine=Engine(project,read_only=True);base=engine.query(intent)
    if base.get('status')!='ok':return base
    conditions=[AggregateFilter.model_validate(x) for x in filters]
    paging=Page.model_validate(page or {})
    if len(conditions)>3 or any(c.metric not in intent['metrics'] for c in conditions):raise ValueError('UNSUPPORTED_AGGREGATE_FILTER')
    ops={'gte':'>=','gt':'>','lte':'<=','lt':'<','eq':'='}
    where=' AND '.join('"'+c.metric+'" '+ops[c.op]+' ?' for c in conditions) or 'TRUE'
    sql='SELECT * FROM ('+base['sql']+') AS controlled_aggregate WHERE '+where
    params=[c.value for c in conditions]
    # Must match the read-only MetricFlow connection already open in this process.
    con=duckdb.connect(str(Path(project).resolve()/'data.duckdb'),read_only=True,config=READ_ONLY)
    try:
        cursor=con.execute(sql,params);rows=[[str(v) if hasattr(v,'isoformat') else v for v in r] for r in cursor.fetchall()];native_columns=[c[0] for c in cursor.description]
    finally:con.close()
    # Native dimension order follows the generated query. Sort all group values,
    # then metrics, to make offset pages deterministic in the frozen snapshot.
    rows.sort(key=lambda r:tuple((v is None,str(v)) for v in r))
    total=len(rows);selected=rows if _all else rows[paging.offset:paging.offset+paging.limit]
    token=hashlib.sha256(json.dumps({'sql':sql,'params':params,'data':base['data_sha256'],'library':base['catalog_sha256']},sort_keys=True).encode()).hexdigest()
    return {**base,'rows':selected,'aggregate_sql':sql,'aggregate_parameters':params,'native_columns':native_columns,
            'page':{'offset':paging.offset,'limit':paging.limit,'total':total,'returned':len(selected),'next_offset':paging.offset+len(selected) if paging.offset+len(selected)<total else None,'complete':paging.offset==0 and len(selected)==total,'snapshot_token':token}}
