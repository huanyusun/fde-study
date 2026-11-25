"""Small, local LlamaIndex knowledge store. No external embedding or model call."""
import hashlib,json,re,shutil
from datetime import date
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def local_transformations():
    from llama_index.core.schema import TransformComponent
    class AlreadyChunked(TransformComponent):
        def __call__(self,nodes,**kwargs):return nodes
    # Nodes are already split into verbatim paragraphs. Avoid constructing the
    # default sentence parser, which would fetch a tokenizer on first use.
    return [AlreadyChunked()]
def tokens(text):
    result=set(re.findall(r'[a-z0-9_]+',text.lower()))
    for phrase in re.findall(r'[\u4e00-\u9fff]+',text):
        for n in [2,3,4]:result.update(phrase[i:i+n] for i in range(max(0,len(phrase)-n+1)))
    return result

def build(catalog_path,output):
    from llama_index.core import SimpleKeywordTableIndex
    from llama_index.core.llms import MockLLM
    from llama_index.core.schema import TextNode
    class LocalKeywordIndex(SimpleKeywordTableIndex):
        def _extract_keywords(self,text):return tokens(text)
    catalog_path=Path(catalog_path).resolve();root=catalog_path.parent;catalog=json.loads(catalog_path.read_text());out=Path(output)
    if out.exists():raise ValueError('NEW_INDEX_VERSION_REQUIRED')
    docs=catalog['documents']
    if not docs or len(docs)>200 or len({d['id'] for d in docs})!=len(docs):raise ValueError('KNOWLEDGE_CATALOG_INVALID')
    nodes=[];sources=[]
    for d in docs:
        if set(d)!={'id','path','version','level','valid_from','valid_until','conditions'}:raise ValueError('KNOWLEDGE_METADATA_REQUIRED')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',d['id']) or not d['version'] or d['level'] not in ['domain','definition','usage']:raise ValueError('KNOWLEDGE_METADATA_INVALID')
        start,end=date.fromisoformat(d['valid_from']),date.fromisoformat(d['valid_until'])
        if start>=end or not isinstance(d['conditions'],dict):raise ValueError('KNOWLEDGE_CONDITIONS_INVALID')
        path=(root/d['path']).resolve()
        if root not in path.parents or path.suffix!='.md':raise ValueError('KNOWLEDGE_SOURCE_OUTSIDE_CATALOG')
        body=path.read_text();source_hash=sha(path)
        for number,chunk in enumerate(re.split(r'\n\s*\n',body),1):
            if chunk.strip():
                meta={k:d[k] for k in ['id','version','level','valid_from','valid_until','conditions']}
                meta.update(source_file=d['path'],source_sha256=source_hash,chunk=number)
                nodes.append(TextNode(id_=d['id']+'-'+str(number),text=chunk,metadata=meta,excluded_llm_metadata_keys=list(meta),excluded_embed_metadata_keys=list(meta)))
        sources.append((path,d['id']+'.md',source_hash))
    if len(nodes)>1000:raise ValueError('KNOWLEDGE_CHUNK_LIMIT')
    out.mkdir(parents=True);(out/'sources').mkdir()
    for path,name,_ in sources:shutil.copy2(path,out/'sources'/name)
    index=LocalKeywordIndex(nodes=nodes,llm=MockLLM(),show_progress=False,transformations=local_transformations())
    index.storage_context.persist(persist_dir=str(out/'index'))
    manifest={'version':catalog['version'],'module_version':'w05-local-keyword-1','documents':len(docs),'chunks':len(nodes),
        'catalog_sha256':sha(catalog_path),'files':{p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()},
        'retrieval':'LlamaIndex keyword table with Chinese 2/3/4-grams; explicit applicability checks; no semantic-vector recall claim'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',newline='\n')
    return manifest

def retrieve(index_path,query,reference_date,*,context=None,level=None,limit=5):
    from llama_index.core import StorageContext,load_index_from_storage
    from llama_index.core.llms import MockLLM
    from llama_index.core.indices.keyword_table.retrievers import KeywordTableSimpleRetriever
    class LocalRetriever(KeywordTableSimpleRetriever):
        def _get_keywords(self,text):return sorted(tokens(text))
    root=Path(index_path);manifest=json.loads((root/'manifest.json').read_text())
    if not query.strip() or len(query)>2000 or type(limit) is not int or not 1<=limit<=20:raise ValueError('KNOWLEDGE_QUERY_INVALID')
    if level is not None and level not in ['domain','definition','usage']:raise ValueError('KNOWLEDGE_LEVEL_INVALID')
    for name,h in manifest['files'].items():
        path=(root/name).resolve()
        if root.resolve() not in path.parents or sha(path)!=h:raise ValueError('KNOWLEDGE_INDEX_HASH_MISMATCH')
    ref=date.fromisoformat(reference_date);context=context or {}
    index=load_index_from_storage(StorageContext.from_defaults(persist_dir=str(root/'index')),llm=MockLLM(),transformations=local_transformations())
    hits=LocalRetriever(index,num_chunks_per_query=1000).retrieve(query)
    result=[]
    for hit in hits:
        m=hit.node.metadata
        if not date.fromisoformat(m['valid_from'])<=ref<date.fromisoformat(m['valid_until']):continue
        if level and m['level']!=level:continue
        conditions=m['conditions']
        if any(k in context and context[k] not in (v if isinstance(v,list) else [v]) for k,v in conditions.items()):continue
        applicable=all(k in context for k in conditions)
        result.append({'node_id':hit.node.node_id,'quote':hit.node.text,'source':m,'applicability':'applicable' if applicable else 'conditional',
            'missing_conditions':[k for k in conditions if k not in context],
            'match_count':len(tokens(query)&tokens(hit.node.text))})
    result.sort(key=lambda r:(-r['match_count'],r['node_id']));result=result[:limit]
    return {'status':'ok' if result else 'not_found','hits':result,'knowledge_version':manifest['version'],'index_sha256':sha(root/'manifest.json'),
        'hard_constraints_from_program':True,'retrieval':'local keyword retrieval'}
