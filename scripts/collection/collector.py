"""Local, on-demand EZIWORK collection engine. No daemon or scheduled jobs."""
import argparse
import datetime as D
import hashlib
import html
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager

from adapters import CollectionError, parse, request_url
from quality import normalize, validate_input
from scope_validation import lh_parameters,validate_lh_scope,lot

ROOT=Path(__file__).resolve().parent
VERSION='2.3.0'
ENV_NAMES=['DATA_GO_KR_SERVICE_KEY','VWORLD_API_KEY','KOSIS_API_KEY','RONE_API_KEY','ECOS_API_KEY']

def now(): return D.datetime.now(D.timezone.utc).isoformat()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(data): return hashlib.sha256(data).hexdigest()
def encoded(data): return json.dumps(data,ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf-8')
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_bytes(encoded(data))
    try:
        for attempt in range(5):
            try:
                os.replace(tmp,path);break
            except PermissionError:
                if os.name!='nt' or attempt==4:raise
                time.sleep(0.05*(2**attempt))
    finally:
        if tmp.exists():tmp.unlink()

class Redactor:
    def __init__(self, values=()):
        self.values=set()
        for value in values:
            if value:
                self.values.update([value,urllib.parse.unquote(value),urllib.parse.quote(value,safe=''),urllib.parse.quote_plus(value)])
    def text(self,value):
        text=str(value)
        for secret in sorted(self.values,key=len,reverse=True): text=text.replace(secret,'[REDACTED]')
        return re.sub(r'(?i)(serviceKey|apiKey|confmKey|OC|KEY)=([^&\s<>"\']+)',r'\1=[REDACTED]',text)
    def data(self,value):
        if isinstance(value,dict): return {k:self.data(v) for k,v in value.items()}
        if isinstance(value,list): return [self.data(v) for v in value]
        return self.text(value) if isinstance(value,str) else value

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise CollectionError('REDIRECT_BLOCKED')

class Transport:
    def __init__(self, sleep=time.sleep, opener=None):
        self.sleep=sleep; self.opener=opener or urllib.request.build_opener(NoRedirect()).open; self.attempts=0
    def fetch(self,url):
        for attempt in range(1,4):
            self.attempts+=1
            delay=min(2**attempt,8)
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'Eziwork-Collector/1.0','Accept':'application/json,application/xml,text/xml'})
                with self.opener(req,timeout=20) as r:
                    body=r.read(16_000_001)
                    if len(body)>16_000_000: raise CollectionError('RESPONSE_TOO_LARGE')
                    return body,attempt
            except urllib.error.HTTPError as exc:
                if exc.code in {401,403}: raise CollectionError('AUTH_REJECTED',str(exc.code)) from None
                if exc.code not in {429,500,502,503,504}: raise CollectionError('HTTP_REJECTED',str(exc.code)) from None
                retry=exc.headers.get('Retry-After','') if exc.headers else ''
                if retry.isdigit(): delay=min(int(retry),60)
                if attempt==3: raise CollectionError('RATE_LIMITED' if exc.code==429 else 'SERVER_UNAVAILABLE') from None
            except (TimeoutError,socket.timeout):
                if attempt==3: raise CollectionError('TIMEOUT') from None
            except urllib.error.URLError as exc:
                if not isinstance(exc.reason,(TimeoutError,socket.timeout)): raise CollectionError('TRANSPORT_FAILED') from None
                if attempt==3: raise CollectionError('TIMEOUT') from None
            self.sleep(delay)

def months(start,end):
    try:
        a=D.datetime.strptime(start,'%Y%m'); b=D.datetime.strptime(end,'%Y%m')
        if not re.fullmatch(r'\d{6}',start+'' ) or not re.fullmatch(r'\d{6}',end): raise ValueError()
        count=(b.year-a.year)*12+b.month-a.month+1
        if count<1 or count>84: raise ValueError()
        return [f'{(a.year*12+a.month-1+i)//12:04}{(a.year*12+a.month-1+i)%12+1:02}' for i in range(count)]
    except (ValueError,TypeError): raise CollectionError('INVALID_PERIOD') from None

def registry(version=None):
    if version not in (None,'2.3.0','2.2.0'):raise CollectionError('SOURCE_DEFINITION_VERSION_UNSUPPORTED')
    reg=load(ROOT.parents[1]/'references/legacy/collection-registry-2.2.0.json' if version=='2.2.0' else ROOT/'registry.json')
    return {s['id']:s for s in reg['sources']},reg['reports']

def validate_request(request,sources,reports):
    if request.get('schema_version')!=1: raise CollectionError('REQUEST_SCHEMA_UNSUPPORTED')
    if request.get('report_type') and request['report_type'] not in {r['id'] for r in reports}: raise CollectionError('UNKNOWN_REPORT')
    if not isinstance(request.get('target'),dict) or not request['target'].get('subject_id'): raise CollectionError('TARGET_REQUIRED')
    if not isinstance(request.get('params',{}),dict): raise CollectionError('INVALID_PARAMS')
    if not isinstance(request.get('date_filters',{}),dict) or not isinstance(request.get('source_scopes',{}),dict):
        raise CollectionError('INVALID_SCOPE_CONFIG')
    t=request['target']
    if t.get('pnu') and (not re.fullmatch(r'\d{19}',str(t['pnu'])) or
                         (t.get('lawd_cd') and str(t['pnu'])[:5]!=str(t['lawd_cd'])) or
                         (t.get('lot_number') and str(t['pnu'])[10:]!=lot(t['lot_number']))):
        raise CollectionError('CONFLICTING_TARGET_PNU')
    chosen=request.get('sources')
    if chosen is None:
        raise CollectionError('SOURCE_SELECTION_REQUIRED')
    if not isinstance(chosen,list) or not chosen or len(set(chosen))!=len(chosen) or any(s not in sources for s in chosen): raise CollectionError('INVALID_SOURCES')
    for key,default,maximum in [('max_pages',100,1000),('page_size',1000,1000)]:
        value=request.get(key,default)
        if type(value)!=int or not 1<=value<=maximum: raise CollectionError('INVALID_LIMIT')
    area=request.get('area',{})
    if not isinstance(area,dict): raise CollectionError('INVALID_AREA')
    for v in area.values():
        if not isinstance(v,(int,float)) or not 0<=v<float('inf'): raise CollectionError('INVALID_AREA')
    if area.get('min_sqm',0)>area.get('max_sqm',float('inf')): raise CollectionError('INVALID_AREA')
    return chosen

def parameters(source,request):
    p={**source.get('defaults',{}),**request.get('params',{}).get(source['id'],{})}
    if source['adapter']=='rtms':
        p.update(lawd_cd=request.get('target',{}).get('lawd_cd'),**request.get('period',{}))
    if source['adapter']=='lh':p=lh_parameters(p,request.get('date_filters',{}).get(source['id']))
    # The only secret source is the secure environment, never request files.
    for key in ['serviceKey','ServiceKey','apiKey','confmKey','KEY','OC']:
        if key in p: raise CollectionError('CREDENTIAL_IN_REQUEST')
    return p

def preflight(request,credentials=None):
    sources,reports=registry(); chosen=validate_request(request,sources,reports)
    credentials=credentials if credentials is not None else os.environ
    result=[]
    for id in chosen:
        s=sources[id]; missing=[]
        if s['mode']=='API':
            p=parameters(s,request)
            missing=[k for k in s['required'] if p.get(k) is None or p.get(k)=='']
            if s['id']=='S17' and (p.get('ID') or p.get('MST')):
                missing=[k for k in (['expected_law_name']+(['efYd'] if not p.get('ID') else [])) if not p.get(k)]
            if s['adapter']=='rtms' and not missing:
                months(p['start_ym'],p['end_ym'])
                if not re.fullmatch(r'\d{5}',str(p['lawd_cd'])): missing.append('lawd_cd:five_digits')
            ready=bool(credentials.get(s['credential']))
            status='PARAMS_REQUIRED' if missing else 'KEY_MISSING' if not ready else 'READY_TO_TEST'
        else:
            status='BROWSER_REQUIRED' if s['mode']=='BROWSER' else 'INPUT_REQUIRED';ready=None
        result.append(dict(source_id=id,title=s['title'],mode=s['mode'],status=status,
            missing_fields=missing,credential_present=ready,implementation_status=s['implementation_status'],
            production_status=s['production_status'],last_audit=s['last_audit'],next_action=s['next_action'],guide_url=s['guide_url']))
    return result

def ttl(source,period=None,today=None):
    if source['adapter']!='rtms': return 0 # Conservative: other APIs always refresh initially.
    today=today or D.date.today(); ym=int(period[:4])*12+int(period[4:])
    return 86400 if today.year*12+today.month-ym<=2 else 7*86400

def age(timestamp):
    try: return (D.datetime.now(D.timezone.utc)-D.datetime.fromisoformat(timestamp)).total_seconds()
    except (ValueError,TypeError): return float('inf')

@contextmanager
def lock(run):
    run.mkdir(parents=True,exist_ok=True);p=run/'.lock'
    try: f=p.open('x',encoding='utf-8')
    except FileExistsError: raise CollectionError('RUN_LOCKED') from None
    try:
        with f: f.write(str(os.getpid()))
        yield
    finally: p.unlink(missing_ok=True)

class Engine:
    def __init__(self, output=ROOT/'runs', cache=ROOT/'cache', transport=None, credentials=None):
        self.output=Path(output);self.cache=Path(cache);self.transport=transport or Transport()
        self.credentials=credentials if credentials is not None else os.environ
        self.redactor=Redactor(self.credentials.get(k) for k in ENV_NAMES)
        self.sources,self.reports=registry()
    def save(self,path,data): write(path,self.redactor.data(data))
    def chunk(self,source,params,run,force=False):
        if source['adapter']=='vworld_address':
            from public_evidence import collect_address
            return collect_address(source,params,run,self.credentials.get('VWORLD_API_KEY',''))
        spec=dict(version=VERSION,source=source['id'],endpoint=source['endpoint'],params=params)
        key=digest(encoded(spec));cache_file=self.cache/(key+'.json')
        checkpoint=run/'checkpoints'/source['id']/(key+'.json')
        lifetime=ttl(source,params.get('month'))
        cached=False; state=None; warnings=[]; initial_attempts=getattr(self.transport,'attempts',0)
        candidates=[] if force else [(cache_file,lifetime,True),(checkpoint,min(lifetime or 3600,3600),False)]
        for file,limit,is_cache in candidates:
            if state is not None or not limit or not file.exists(): continue
            try:
                c=load(file)
                if not 0<=age(c['observed_at'])<limit or (is_cache and not c['complete']): continue
                count=0; page_hashes=set()
                for index,page in enumerate(c['pages'],1):
                    body=page['body'].encode('utf-8'); parsed=parse(source,body)
                    if source['adapter']=='lh':validate_lh_scope(parsed,params)
                    hashed=digest(encoded(parsed.rows))
                    if page['page']!=index or digest(body)!=page['sha256'] or page['rows']!=len(parsed.rows):
                        raise CollectionError('CHECKPOINT_HASH_MISMATCH')
                    if parsed.total!=c['total'] or (parsed.rows and hashed in page_hashes):
                        raise CollectionError('CHECKPOINT_COUNT_MISMATCH')
                    count+=len(parsed.rows);page_hashes.add(hashed)
                if c['complete'] and c['total'] is not None and count!=c['total']:
                    raise CollectionError('CHECKPOINT_COUNT_MISMATCH')
                state=c;cached=is_cache
            except (CollectionError,OSError,ValueError,KeyError,TypeError):
                warnings.append('CORRUPT_CACHE_IGNORED' if is_cache else 'CORRUPT_CHECKPOINT_IGNORED')
        state=state or dict(observed_at=now(),complete=False,pages=[],total=None,error=None)
        state['error']=None; hashes=set(); rows=[]; attempts=0
        # Replay validated pages from checkpoint/cache; raw evidence is materialized in this run.
        for page in state['pages']:
            body=page['body'].encode('utf-8')
            if digest(body)!=page['sha256']: raise CollectionError('CHECKPOINT_HASH_MISMATCH')
            parsed=parse(source,body); rows.extend(parsed.rows)
            hashes.add(digest(encoded(parsed.rows)))
        page_size=params.pop('_page_size',1000) if '_page_size' in params else 1000
        max_pages=params.pop('_max_pages',100) if '_max_pages' in params else 100
        try:
            while not state['complete']:
                index=len(state['pages'])+1
                if index>max_pages: raise CollectionError('PAGE_LIMIT_REACHED')
                attempts+=1
                body,n=self.transport.fetch(request_url(source,params,index,page_size,self.credentials[source['credential']]))
                attempts+=n-1
                # Redact echoed credentials before either raw or checkpoint persistence.
                body=self.redactor.text(body.decode('utf-8-sig')).encode('utf-8')
                parsed=parse(source,body); content_hash=digest(encoded(parsed.rows))
                if source['adapter']=='lh':
                    try:validate_lh_scope(parsed,params)
                    except CollectionError as exc:
                        rejected=run/'raw_rejected'/source['id']/f'{key}_p{index}.txt'
                        rejected.parent.mkdir(parents=True,exist_ok=True);rejected.write_bytes(body)
                        self.save(rejected.with_suffix('.json'),dict(error=exc.code,requested=params,applied=parsed.query_scope))
                        raise
                if parsed.rows and content_hash in hashes: raise CollectionError('REPEATED_PAGE')
                if state['total'] is not None and parsed.total!=state['total']: raise CollectionError('TOTAL_COUNT_CHANGED')
                state['total']=parsed.total
                if not parsed.rows and state['total'] not in (0,len(rows)): raise CollectionError('EARLY_EMPTY_PAGE')
                hashes.add(content_hash);rows.extend(parsed.rows)
                state['pages'].append(dict(page=index,body=body.decode('utf-8'),sha256=digest(body),rows=len(parsed.rows),code=parsed.code))
                if parsed.total is not None:
                    if len(rows)>parsed.total: raise CollectionError('COUNT_MISMATCH')
                    state['complete']=len(rows)==parsed.total
                elif parsed.terminal: state['complete']=True
                else: raise CollectionError('TOTAL_COUNT_REQUIRED')
                self.save(checkpoint,state)
        except (CollectionError,UnicodeError) as exc:
            state['error']=exc.code if isinstance(exc,CollectionError) else 'RESPONSE_ENCODING_INVALID'
            state['complete']=False
        self.save(checkpoint,state)
        if state['complete'] and lifetime and not cached: self.save(cache_file,state)
        materialized=[]
        normalization_request=load(run/'request.json')
        for page in state['pages']:
            raw=run/'raw'/source['id']/f'{key}_p{page["page"]}.txt'
            raw.parent.mkdir(parents=True,exist_ok=True);raw.write_text(page['body'],encoding='utf-8')
            parsed=parse(source,page['body'].encode('utf-8'))
            verified_scope=validate_lh_scope(parsed,params) if source['adapter']=='lh' else None
            for row in parsed.rows:
                materialized.append(normalize(source,row,normalization_request,str(raw.relative_to(run)),state['observed_at'],params.get('month'),verified_scope))
        scope_proof=normalization_request.get('scope_evidence',{}).get(source['id'])
        archived_proof=None
        if scope_proof:
            original=Path(scope_proof.get('file',''))
            if original.is_file() and original.stat().st_size<=16_000_000 and digest(original.read_bytes())==scope_proof.get('sha256'):
                target=run/'raw'/source['id']/('metadata-'+scope_proof['sha256']+original.suffix)
                target.parent.mkdir(parents=True,exist_ok=True)
                content=original.read_bytes()
                if any(secret.encode('utf-8') in content for secret in self.redactor.values):raise CollectionError('CREDENTIAL_IN_METADATA')
                target.write_bytes(content)
                archived_proof={**scope_proof,'file':None,'archived_file':str(target.relative_to(run))}
        for record in materialized:
            if archived_proof:record['provenance']['scope_evidence']=archived_proof
            raw=run/record['provenance']['raw_file']
            record['provenance'].update(raw_sha256=digest(raw.read_bytes()),
                processing_status='VALIDATED' if record['usable'] else 'EXTRACTED_REVIEW_REQUIRED')
        return dict(status='COMPLETE' if state['complete'] else 'PARTIAL' if materialized else state['error'] or 'FAILED',
            complete=state['complete'],rows=materialized,returned_count=len(rows) if state['pages'] else None,total_count=state['total'],
            error=state['error'],warnings=warnings,cached=cached,network_attempts=getattr(self.transport,'attempts',initial_attempts+attempts)-initial_attempts,observed_at=state['observed_at'])
    def collect(self,request,run_id=None,resume=False,force=False):
        started=time.monotonic()
        chosen=validate_request(request,self.sources,self.reports)
        run_id=run_id or D.datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id): raise CollectionError('INVALID_RUN_ID')
        run=self.output/run_id
        if run.exists() and not resume: raise CollectionError('RUN_EXISTS_USE_RESUME')
        with lock(run):
            if (run/'request.json').exists():
                if load(run/'request.json')!=request: raise CollectionError('RESUME_REQUEST_MISMATCH')
            else: self.save(run/'request.json',request)
            manifest=load(run/'manifest.json') if (run/'manifest.json').exists() else dict(schema_version=1,version=VERSION,run_id=run_id,created_at=now(),sources={})
            for item in preflight(request,self.credentials):
                id=item['source_id'];source=self.sources[id]
                if source['mode']!='API':
                    manifest['sources'].setdefault(id,{**item,'complete':False,'usable_count':0,'returned_count':None});continue
                if item['status']!='READY_TO_TEST':
                    manifest['sources'][id]={**item,'complete':False,'usable_count':0,'returned_count':None};continue
                p=parameters(source,request)
                periods=months(p['start_ym'],p['end_ym']) if source['adapter']=='rtms' else [None]
                chunks=[];all_rows=[]
                for period in periods:
                    cp=dict(p)
                    if period: cp['month']=period
                    cp.update(_page_size=request.get('page_size',1000),_max_pages=request.get('max_pages',100))
                    result=self.chunk(source,cp,run,force);all_rows.extend(result.pop('rows'));chunks.append(result)
                    # Stop remaining months on credential or schema errors.
                    if result['error'] in {'AUTH_REJECTED','AUTH_APPROVAL_REQUIRED','KEY_MISSING','KEY_NOT_REGISTERED','CREDENTIAL_EXPIRED_CONFIRMED','REQUEST_CONFIG_INVALID','ENDPOINT_UNAVAILABLE','RESPONSE_SCHEMA_CHANGED'}: break
                complete=len(chunks)==len(periods) and all(c['complete'] for c in chunks)
                usable=sum(r['usable'] for r in all_rows) if complete else 0
                for row in all_rows:
                    if not complete: row['usable']=False;row['issues'].append('INCOMPLETE_SOURCE_COLLECTION')
                self.save(run/'normalized'/f'{id}.json',all_rows)
                manifest.pop('requirement_reviews',None)
                manifest['sources'][id]=dict(source_id=id,title=source['title'],status='COMPLETE' if complete else 'PARTIAL' if all_rows else chunks[-1]['error'],
                    complete=complete,returned_count=len(all_rows) if any(c['returned_count'] is not None for c in chunks) else None,usable_count=usable,
                    normalized_file=f'normalized/{id}.json',chunks=chunks,updated_at=now(),
                    implementation_status=source['implementation_status'],production_status='LIVE_COLLECTION_CHECKED' if complete else 'AWAITING_LIVE_VALIDATION')
                self.save(run/'manifest.json',manifest)
            manifest['updated_at']=now();manifest['elapsed_seconds']=round(time.monotonic()-started,4);manifest['readiness']=report_readiness(request,manifest,self.reports)
            self.save(run/'manifest.json',manifest); dashboard(run,manifest,self.sources,self.reports)
        return run,manifest
    def import_file(self,request,path,run_id=None):
        payload=load(path);source=self.sources.get(payload.get('source_id'))
        if source is None: raise CollectionError('INPUT_ROUTE_REQUIRED')
        validate_request(request,self.sources,self.reports)
        run_id=run_id or D.datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id): raise CollectionError('INVALID_RUN_ID')
        run=self.output/run_id
        with lock(run):
            if not (run/'manifest.json').exists():
                if (run/'request.json').exists() and load(run/'request.json')!=request: raise CollectionError('RESUME_REQUEST_MISMATCH')
                self.save(run/'request.json',request)
                self.save(run/'manifest.json',dict(schema_version=1,version=VERSION,run_id=run.name,created_at=now(),sources={}))
            if load(run/'request.json')!=request: raise CollectionError('RESUME_REQUEST_MISMATCH')
            if source['id'] not in validate_request(request,self.sources,self.reports): raise CollectionError('SOURCE_OUTSIDE_REQUEST')
            from public_evidence import review_official_payload
            if source['id'] in ('S07','S12','S17'):
                review_official_payload(payload,Path(path).parent,request)
            rows,issues=validate_input(source,payload,request)
            raw=run/'raw'/source['id']/(uuid.uuid4().hex+'.json')
            api_file=source['mode']=='API'
            if api_file:
                if payload.get('api_file_mode') is not True or payload.get('native_units_confirmed') is not True or not payload.get('attachments'):
                    issues.append('OFFICIAL_FILE_AND_NATIVE_UNITS_REQUIRED')
                rows=[normalize(source,r,request,str(raw.relative_to(run)),now()) for r in payload.get('records',[]) if isinstance(r,dict)]
                for row in rows:
                    row['provenance'].update(source_url=payload.get('source_url'),review_status=payload.get('review_status'),
                        evidence_mode=payload.get('evidence_mode'),issued_at=payload.get('issued_at'))
                    if payload.get('evidence_mode')!='ACTUAL': row['usable']=False
            if source['id'] in ('S12','S17'):
                rows=[normalize(source,r,request,str(raw.relative_to(run)),now()) for r in payload.get('records',[]) if isinstance(r,dict)]
                for row in rows:
                    row['provenance'].update(source_url=payload.get('source_url'),review_status=payload.get('review_status'),
                        evidence_mode=payload.get('evidence_mode'),collection_channel='FILE')
                    if payload.get('evidence_mode')!='ACTUAL':row['usable']=False
            attachments=payload.get('attachments',[])
            evidence=payload.get('observation',{}).get('evidence_files',[])
            for entry in attachments+[{ 'file':f } for f in evidence]:
                relative=entry.get('file') if isinstance(entry,dict) else None
                if not isinstance(relative,str): issues.append('INVALID_EVIDENCE_FILE');continue
                base=Path(path).resolve().parent; original=(base/relative).resolve()
                if not original.is_relative_to(base) or not original.is_file(): issues.append('EVIDENCE_FILE_MISSING');continue
                if original.stat().st_size>30_000_000: issues.append('EVIDENCE_FILE_TOO_LARGE');continue
                data=original.read_bytes();sha=digest(data)
                if any(secret.encode('utf-8') in data for secret in self.redactor.values):
                    issues.append('CREDENTIAL_IN_EVIDENCE_FILE');continue
                if entry.get('sha256') and entry['sha256']!=sha: issues.append('EVIDENCE_HASH_MISMATCH');continue
                evidence_path=run/'raw'/source['id']/(sha+original.suffix)
                evidence_path.parent.mkdir(parents=True,exist_ok=True);evidence_path.write_bytes(data)
                entry['archived_file']=str(evidence_path.relative_to(run));entry['sha256']=sha
            if issues:
                for row in rows: row['usable']=False
            self.save(raw,payload)
            for row in rows:
                row['provenance'].update(raw_file=str(raw.relative_to(run)),raw_sha256=digest(raw.read_bytes()),observed_at=now(),
                    attachments=[{'archived_file':a['archived_file'],'sha256':a['sha256']} for a in attachments if 'archived_file' in a],
                    processing_status='VALIDATED' if row['usable'] and not issues else 'EXTRACTED_REVIEW_REQUIRED')
            self.save(run/'normalized'/f'{source["id"]}.json',rows)
            manifest=load(run/'manifest.json')
            manifest.pop('requirement_reviews',None)
            complete=not issues and (api_file or all(not r['issues'] for r in rows))
            if not complete:
                for row in rows: row['usable']=False
            self.save(run/'normalized'/f'{source["id"]}.json',rows)
            manifest['sources'][source['id']]=dict(source_id=source['id'],title=source['title'],
                status='IMPORTED' if complete else 'REVIEW_REQUIRED',complete=complete,
                returned_count=len(rows),usable_count=sum(r['usable'] for r in rows) if complete else 0,
                issues=issues,normalized_file=f'normalized/{source["id"]}.json',updated_at=now(),
                observation=payload.get('observation'),implementation_status='IMPLEMENTED',
                production_status=('OFFICIAL_FILE_REVIEWED' if api_file else 'ACTUAL_INPUT_REVIEWED') if complete else 'AWAITING_REVIEW')
            manifest['readiness']=report_readiness(request,manifest,self.reports);manifest['updated_at']=now()
            self.save(run/'manifest.json',manifest);dashboard(run,manifest,self.sources,self.reports)
        return run,manifest

def report_readiness(request,manifest,reports):
    results=[]
    for report in reports:
        groups=[]
        for group in report['data_requirements']:
            used=[s for s in group['sources'] if manifest['sources'].get(s,{}).get('complete') and manifest['sources'][s].get('usable_count',0)>0]
            required=group['role'].startswith('필수') or ('필수' in group['role'] and group['data'] in request.get('required_groups',[]))
            review=manifest.get('requirement_reviews',{}).get(group['requirement_id'],{})
            reviewed=review.get('review_status')=='VERIFIED' and set(review.get('sources',[]))<=set(used) and bool(review.get('sources'))
            groups.append(dict(requirement_id=group['requirement_id'],data=group['data'],required=required,
                status='AVAILABLE' if reviewed else 'HOLD' if required else 'EXCLUDED',
                sources=review.get('sources',[]) if reviewed else [],collected_sources=used,
                coverage_status='VERIFIED' if reviewed else 'COLLECTED_PENDING_COVERAGE_REVIEW' if used else 'MISSING',
                coverage_checklist=group['coverage_checklist'],missing_handling=group['missing_handling']))
        results.append(dict(report_id=report['id'],title=report['title'],status='HOLD' if any(g['status']=='HOLD' for g in groups) else 'READY_WITH_DECLARED_SCOPE',groups=groups))
    return results

def dashboard(run,manifest,sources,reports):
    esc=lambda x:html.escape(str(x))
    labels={'COMPLETE':'전체 조회 완료','PARTIAL':'부분 수집','KEY_MISSING':'인증키 필요','AUTH_REJECTED':'인증 거절',
            'BROWSER_REQUIRED':'브라우저 연결 필요','INPUT_REQUIRED':'자료 입력 필요','PARAMS_REQUIRED':'조회 조건 필요',
            'IMPORTED':'입력 검증 완료','REVIEW_REQUIRED':'자료 검토 필요','NOT_REQUESTED':'이번 실행 미요청','READY_TO_TEST':'실제 검증 대기'}
    rows=[]
    production_labels={'LIVE_COLLECTION_CHECKED':'실제 API 수신 확인','AWAITING_LIVE_VALIDATION':'실제 운영 검증 대기',
        'ACTUAL_INPUT_REVIEWED':'실제 입력자료 대조 완료','OFFICIAL_FILE_REVIEWED':'공식 파일 대조 완료','AWAITING_REVIEW':'자료 검토 대기'}
    for id,s in sources.items():
        r=manifest['sources'].get(id,{});status=r.get('status','NOT_REQUESTED')
        guide=s['guide_url'] or os.path.relpath(ROOT/'forms'/f'{id}.json',run).replace('\\','/')
        impl='어댑터 구현 · 설정 필요' if s['implementation_status']=='ADAPTER_IMPLEMENTED_CONFIG_REQUIRED' else '구현됨'
        production=r.get('production_status',s['production_status'])
        rows.append(f'<tr data-search="{esc(id+" "+s["title"]+" "+status+" "+labels.get(status,status))}"><td>{esc(id)}</td><td>{esc(s["title"])}</td><td>{esc(s["mode"])}</td><td>{esc(impl)}</td><td>{esc(labels.get(status,status))}</td><td>{esc(r.get("returned_count") if r.get("returned_count") is not None else "미수집")}</td><td>{esc(r.get("usable_count",0))}</td><td>{esc(production_labels.get(production,production))}<br><small>{esc(r.get("verification_scope",""))}</small></td><td><a href="{esc(guide)}">안내서 / 입력 양식</a><br>{esc(r.get("next_action",s["next_action"]))}</td></tr>')
    gates=''.join(f'<details><summary>{esc(r["report_id"]+" "+r["title"]+" · "+r["status"])}</summary><ul>'+''.join(f'<li>{esc(g["data"]+" · "+g["status"])} — {esc(g["missing_handling"])}</li>' for g in r['groups'])+'</ul></details>' for r in manifest.get('readiness',[]))
    document='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>EZIWORK 수집 상태</title><style>body{font-family:Malgun Gothic,sans-serif;margin:0;background:#f3f5f7;color:#142a3b}main{max-width:1400px;margin:auto;padding:28px}h1{font-size:30px}input{padding:12px;width:min(90%,480px);border:1px solid #9aaebc;border-radius:6px}.table{overflow:auto;background:white;margin:24px 0}table{border-collapse:collapse;width:100%;min-width:900px;font-size:13px}th,td{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid #dce3e8}th{background:#17394a;color:white}details{background:white;padding:16px;margin:8px 0}a{color:#00736b}p{line-height:1.7}small{color:#536b7b}</style><main><small>EZIWORK · COLLECTION OPERATIONS</small><h1>전체 40개 수집 경로</h1><p>실행: RUN_ID<br>구현 상태와 실제 연결 검증 상태를 분리합니다. 미수집은 0건이 아닙니다. 표본 수신·전체 조회·보고서 사용 가능 건수도 서로 다릅니다.</p><input id="search" placeholder="출처명·ID·상태 검색" aria-label="출처 검색"><div class="table"><table><thead><tr><th>ID</th><th>출처</th><th>방식</th><th>현재 상태</th><th>수신 건수</th><th>사용 가능</th><th>운영 검증</th><th>보완 안내</th></tr></thead><tbody>ROWS</tbody></table></div><h2>보고서 자료 준비 상태</h2>GATES<p>고객 보고서 제작 전 manifest.json의 readiness와 정규화 자료의 usable을 함께 확인하세요.</p></main><script>document.querySelector('#search').addEventListener('input',e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.dataset.search.toLowerCase().includes(q))})</script></html>'''
    document=document.replace('RUN_ID',esc(manifest['run_id'])).replace('ROWS',''.join(rows)).replace('GATES',gates)
    document=document.replace('<th>방식</th>','<th>방식</th><th>구현 상태</th>')
    document=document.replace('min-width:900px','min-width:1200px').replace('th{background:','th{white-space:nowrap;background:')
    if manifest.get('overview_only'):
        document=document.replace('<h2>보고서 자료 준비 상태</h2>','<h2>검증 범위</h2><p>출처별 연결 점검을 모은 화면입니다. 서로 다른 대상의 자료를 합쳐 보고서를 만들지 않습니다. 14개 보고서·58개 자료 요구사항의 준비 판정은 개별 실행에서 확인합니다.</p>')
    (run/'status.html').write_text(document,encoding='utf-8')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'runs');parser.add_argument('--cache',type=Path,default=ROOT/'cache')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ['preflight','collect','import']:
        p=sub.add_parser(name);p.add_argument('--request',required=True,type=Path)
        if name!='preflight': p.add_argument('--run-id')
        if name=='collect': p.add_argument('--resume',action='store_true');p.add_argument('--force-refresh',action='store_true')
        if name=='import': p.add_argument('--file',required=True,type=Path)
    p=sub.add_parser('status');p.add_argument('--run-id',required=True)
    args=parser.parse_args()
    if args.command in ('preflight','collect','import'):
        sys.path.insert(0,str(ROOT.parent))
        import key_environment
        try:
            needs_keys=args.command!='import' or load(args.file).get('evidence_mode')=='ACTUAL'
            blocked=key_environment.require_registered() if needs_keys else None
        except (ValueError,OSError):
            print(json.dumps({'status':'KEY_STORE_REVIEW_REQUIRED'}));return 2
        if blocked:print(json.dumps(blocked,ensure_ascii=False,indent=2));return 2
    engine=Engine(args.output,args.cache)
    try:
        if args.command=='status':
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',args.run_id): raise CollectionError('INVALID_RUN_ID')
            run=args.output/args.run_id;m=load(run/'manifest.json');dashboard(run,m,engine.sources,engine.reports);result=m
        else:
            request=load(args.request)
            if args.command=='preflight': result={'sources':preflight(request)}
            else:
                run,m=engine.collect(request,args.run_id,args.resume,args.force_refresh) if args.command=='collect' else engine.import_file(request,args.file,args.run_id)
                result=dict(run=str(run.resolve()),sources=[{k:v for k,v in s.items() if k not in ['chunks','observation']} for s in m['sources'].values()],status_page=str((run/'status.html').resolve()))
        print(json.dumps(engine.redactor.data(result),ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except (CollectionError,OSError,ValueError,TypeError,KeyError):
        exc=sys.exc_info()[1];code=exc.code if isinstance(exc,CollectionError) else 'INVALID_INPUT_OR_LOCAL_IO'
        print(json.dumps({'status':code},ensure_ascii=False));return 2

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
