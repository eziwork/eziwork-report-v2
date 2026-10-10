"""Portable report workflow. Text/analysis is authored by Codex; this CLI never calls an AI API."""
from pathlib import Path
import argparse, contextlib, getpass, hashlib, html, json, math, os, platform, re, shutil, statistics, subprocess, sys
from importlib.metadata import version, PackageNotFoundError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(os.environ.get('EZIWORK_RUNTIME_DIR',ROOT/'runtime'))/'python'))
sys.path.insert(0,str(ROOT/'scripts/collection'))
import collector
import covers
import integrations
import key_environment
from adapters import CollectionError
ALLOWED=collector.ENV_NAMES
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,d):collector.write(Path(p),d)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def credentials():
 result={}
 if os.environ.get('EZIWORK_DISABLE_BUNDLED_KEYS','').lower() not in ('1','true','yes'):
  result.update(load(ROOT/'config/default-credentials.json'))
 local=Path(os.environ.get('EZIWORK_CREDENTIAL_FILE',ROOT/'config/local-credentials.json'))
 if local.is_file():result.update(load(local))
 result.update(key_environment.user_values(ALLOWED))
 return {k:os.environ.get(k,'').strip() or result.get(k,'') for k in ALLOWED if os.environ.get(k,'').strip() or result.get(k,'')}
@contextlib.contextmanager
def environment():
 before={k:os.environ.get(k) for k in ALLOWED};values=credentials()
 try:
  os.environ.update(values);yield collector.Redactor(values.values())
 finally:
  for k,v in before.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
def node():
 p=os.environ.get('EZIWORK_NODE') or shutil.which('node')
 if not p:raise ValueError('NODE_REQUIRED: install Node.js, or set EZIWORK_NODE')
 return p
def privacy_issues(path):
 """Conservative local signal detection, not a guarantee of anonymity."""
 path=Path(path)
 if path.suffix.lower()=='.pdf':
  from pypdf import PdfReader
  text='\n'.join(p.extract_text() or '' for p in PdfReader(path).pages)
  if not text.strip():return ['IMAGE_PDF_REQUIRES_REDACTED_TEXT_COPY']
 elif path.suffix.lower() in ('.json','.csv','.txt'):
  try:text=path.read_text(encoding='utf-8-sig')
  except UnicodeDecodeError:text=path.read_text(encoding='cp949')
 else:return ['USE_REDACTED_JSON_CSV_TEXT_OR_TEXT_PDF']
 issues=[]
 for code,pat in [('RESIDENT_ID',r'\b\d{6}\s*[- ]?\s*[1-8]\d{6}\b'),('PERSONAL_CONTACT',r'(?<!\d)01[016789][ -]?\d{3,4}[ -]?\d{4}(?!\d)'),('EMAIL',r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}'),('PERSONAL_FIELD',r'"(?:tenant_name|owner_name|resident_id|account_number|phone|email)"\s*:\s*"[^"\s]+"')]:
  if re.search(pat,text):issues.append(code)
 return issues
def check_contract(path):
 path=Path(path).resolve();c=load(path)
 if c.get('schema_version')!=1 or c.get('report_id') not in [f'P{i:02}' for i in range(1,15)]:raise ValueError('CONTRACT_SCHEMA')
 if c.get('mode') not in ['actual','historical_replay','synthetic_test']:raise ValueError('MODE_REQUIRED')
 if not c.get('question') or not c.get('basis_date') or not c.get('scope'):raise ValueError('QUESTION_DATE_SCOPE_REQUIRED')
 ds=(path.parent/c['dataset']).resolve()
 if not ds.is_file() or sha(ds)!=c.get('dataset_sha256'):raise ValueError('DATASET_CHANGED')
 data=load(ds)
 if c['mode']=='actual':
  if data.get('status')!='READY_WITH_DECLARED_SCOPE':raise ValueError('EVIDENCE_NOT_READY')
  if data.get('report_id')!=c['report_id'] or not c.get('target') or c['target']!=data.get('target'):raise ValueError('REPORT_TARGET_MISMATCH')
  from evidence_rules import RULE_VERSION,revalidate
  if data.get('validation_rule_version')!=RULE_VERSION:raise ValueError('EVIDENCE_CURRENT_REVIEW_REQUIRED')
  run=ds.parent
  if not (run/'request.json').is_file():raise ValueError('EVIDENCE_ORIGINAL_RUN_REQUIRED')
  request=load(run/'request.json');registry,_=collector.registry()
  if not data.get('records') or any(not revalidate(registry.get(r.get('source_id')),r,request,run) for r in data['records']):
   raise ValueError('EVIDENCE_CURRENT_REVIEW_REQUIRED')
 if data.get('status')=='HOLD':raise ValueError('EVIDENCE_HOLD')
 records=data.get('records',[]);claims={};claim_sources={};claim_units={};sources={x['id']:x for x in c.get('sources',[])}
 if len(sources)!=len(c.get('sources',[])):raise ValueError('DUPLICATE_SOURCE')
 for s in sources.values():
  if not s.get('title') or not s.get('basis_date') or not str(s.get('url','')).startswith(('https://','http://','provided:')):raise ValueError('SOURCE_METADATA')
 for q in c.get('claims',[]):
  id=q['id']
  if id in claims:raise ValueError('DUPLICATE_CLAIM')
  if not q.get('source_ids') or any(s not in sources for s in q['source_ids']):raise ValueError('CLAIM_SOURCE')
  if 'operation' in q:
   vals=[claims[x] for x in q['inputs']]
   input_units={claim_units[x] for x in q['inputs']}
   required_sources=set().union(*(claim_sources[x] for x in q['inputs']))
   if set(q['source_ids'])!=required_sources:raise ValueError('CALCULATION_SOURCE_MISMATCH')
   op=q['operation']
   if op in ['sum','difference','median'] and len(input_units)>1:raise ValueError('CALCULATION_UNIT_MISMATCH')
   unit=next(iter(input_units)) if len(input_units)==1 and op in ['sum','difference','median'] else None
   if op=='sum':v=sum(vals)
   elif op=='difference' and len(vals)==2:v=vals[0]-vals[1]
   elif op=='product':v=math.prod(vals)
   elif op=='ratio' and len(vals)==2 and vals[1]!=0:v=vals[0]/vals[1]
   elif op=='median':v=statistics.median(vals)
   else:raise ValueError('CALCULATION_UNSUPPORTED')
   if not isinstance(q['value'],(int,float)) or not math.isclose(v,q['value'],rel_tol=1e-9,abs_tol=1e-8):raise ValueError('CALCULATION_MISMATCH')
  else:
   i=q['record_index']
   if not isinstance(i,int) or i<0 or i>=len(records):raise ValueError('RECORD_INDEX')
   r=records[i]
   if r.get('usable') is not True:raise ValueError('RECORD_NOT_USABLE')
   if r.get('source_id') not in q['source_ids']:raise ValueError('RECORD_SOURCE_MISMATCH')
   v=r['values'][q['field']]
   if v!=q['value']:raise ValueError('CLAIM_VALUE_MISMATCH')
   unit=r.get('provenance',{}).get('units',r.get('units',{})).get(q['field'])
   if not unit and q['field'].endswith('_krw'):unit='KRW'
   if not unit and q['field'].endswith('_sqm'):unit='m2'
  if unit and q.get('unit') and canonical_unit(unit)!=canonical_unit(q['unit']):raise ValueError('CLAIM_UNIT_MISMATCH')
  claim_units[id]=canonical_unit(unit or q.get('unit'))
  if isinstance(v,float) and not math.isfinite(v):raise ValueError('NONFINITE')
  claims[id]=v
  claim_sources[id]=set(q['source_ids'])
 figures={}
 for f in c.get('figures',[]):
  if f['id'] in figures:raise ValueError('DUPLICATE_FIGURE')
  if f['type'] not in ['bar','dot','building','table']:raise ValueError('FIGURE_TYPE')
  if not f.get('title') or not f.get('unit') or not f.get('points'):raise ValueError('FIGURE_METADATA')
  for text in [f['title'],f.get('note','')]+[p['label'] for p in f['points']]:bound_text(text,claims)
  for p in f['points']:
   v=claims[p['claim_id']]
   if claim_units[p['claim_id']] and canonical_unit(f['unit'])!=claim_units[p['claim_id']]:raise ValueError('CHART_UNIT_MISMATCH')
   if p['value']!=v:raise ValueError('CHART_VALUE_MISMATCH')
   if f['type']!='table' and (not isinstance(v,(int,float)) or isinstance(v,bool)):raise ValueError('CHART_NUMERIC_REQUIRED')
   if f['type']=='building' and (v<0 or int(v)!=v or v>100):raise ValueError('FLOOR_RANGE')
  figures[f['id']]=f
 ids=set()
 for b in c.get('blocks',[]):
  if b['id'] in ids:raise ValueError('DUPLICATE_BLOCK')
  ids.add(b['id'])
  if not b.get('title') or not b.get('paragraphs') or not b.get('claim_ids'):raise ValueError('BLOCK_CONTENT_REQUIRED')
  if any(x not in claims for x in b['claim_ids']) or any(x not in figures for x in b.get('figure_ids',[])):raise ValueError('BLOCK_REFERENCE')
  for text in [b['title']]+b['paragraphs']:
   bound_text(text,claims)
   if any(id not in b['claim_ids'] for id in re.findall(r'\{\{([A-Za-z0-9_-]+)(?::\w+)?\}\}',text)):raise ValueError('BLOCK_CLAIM_NOT_DECLARED')
 if not ids:raise ValueError('NO_BLOCKS')
 if c.get('title'):bound_text(c['title'],claims)
 cover=c.get('cover',{})
 if not isinstance(cover,dict) or ('enabled' in cover and not isinstance(cover['enabled'],bool)):raise ValueError('COVER_SCHEMA')
 if set(cover)-set(covers.FIELDS)-{'enabled'}:raise ValueError('COVER_FIELD_UNKNOWN')
 for field in covers.FIELDS:
  if field in cover:
   if not isinstance(cover[field],str) or not cover[field].strip():raise ValueError('COVER_TEXT_REQUIRED')
   bound_text(cover[field],claims)
 if c.get('qa',{}).get('evidence_review')!='PASS' or c.get('qa',{}).get('copy_review')!='PASS':raise ValueError('CODEX_REVIEW_REQUIRED')
 assets=c.get('assets',[])
 if len({a['id'] for a in assets})!=len(assets):raise ValueError('DUPLICATE_ASSET')
 for asset in assets:
  bound_text(asset['caption'],claims);bound_text(asset['alt'],claims)
  check_asset=dict(asset)
  if asset['kind']=='chart':check_asset['points']=[{**pt,'label':bound_text(pt['label'],claims)} for pt in asset['points']]
  integrations.verify_asset(check_asset,path.parent,claims)
  if asset['kind']=='chart':
   for point in asset['points']:
    bound_text(point['label'],claims)
    if claim_units[point['claim_id']] and canonical_unit(asset['unit'])!=claim_units[point['claim_id']]:raise ValueError('ASSET_UNIT_MISMATCH')
 for b in c.get('blocks',[]):
  if any(i not in {a['id'] for a in assets} for i in b.get('asset_ids',[])):raise ValueError('ASSET_REFERENCE')
 return c
def esc(x):return html.escape(str(x))
def canonical_unit(value):
 return {'KRW':'원','KRW/month':'원/월','m2':'㎡','m²':'㎡','sqm':'㎡'}.get(value,value)
def format_value(value,style='raw'):
 if style=='raw':return str(value)
 if style=='number':return f'{value:,}'
 if style=='krw':
  if not isinstance(value,(int,float)) or int(value)!=value:raise ValueError('KRW_INTEGER_REQUIRED')
  sign='−' if value<0 else '';v=abs(int(value));parts=[]
  for unit,label in [(100000000,'억'),(10000,'만')]:
   q,v=divmod(v,unit)
   if q:parts.append(f'{q:,}{label}')
  if v:parts.append(f'{v:,}')
  return sign+(' '.join(parts) or '0')+'원'
 if style=='percent':return f'{value:g}%'
 raise ValueError('NUMBER_FORMAT_UNSUPPORTED')
def bound_text(text,claims):
 # All numeric spans in customer copy must come from a verified claim token.
 token=r'\{\{([A-Za-z0-9_-]+)(?::(raw|number|krw|percent))?\}\}'
 rest=re.sub(token,'',text)
 if re.search(r'\d',rest):raise ValueError('NUMERIC_TEXT_UNBOUND')
 if '{{' in rest or '}}' in rest:raise ValueError('INVALID_CLAIM_TOKEN')
 return re.sub(token,lambda m:format_value(claims[m[1]],m[2] or 'raw'),text)
def fig_html(f):
 points=f['points'];caption=f'<figcaption>{esc(f["title"])} · {esc(f["unit"])}</figcaption>'
 if f['type']=='table':return '<figure>'+caption+'<table><thead><tr><th>항목</th><th>'+esc(f['unit'])+'</th></tr></thead><tbody>'+''.join(f'<tr><th>{esc(p["label"])}</th><td>{esc(p["value"])}</td></tr>' for p in points)+'</tbody></table></figure>'
 vals=[p['value'] for p in points];low=min(0,min(vals));high=max(0,max(vals));span=high-low or 1
 height=65+len(points)*65;shapes=[]
 for i,p in enumerate(points):
  y=55+i*65;x=190+(p['value']-low)/span*400;zero=190-low/span*400
  shapes.append(f'<text x="10" y="{y+5}">{esc(p["label"])}</text>')
  if f['type']=='dot':shapes.append(f'<circle cx="{x}" cy="{y}" r="7" fill="#2c61ef"/>')
  elif f['type']=='building':
   shapes.append(f'<rect x="200" y="{y-22}" width="36" height="40" fill="#dce7ff"/><text x="250" y="{y+5}">{esc(p["value"])}층</text>')
  else:shapes.append(f'<rect x="{min(x,zero)}" y="{y-12}" width="{abs(x-zero)}" height="24" fill="#2c61ef"/>')
  if f['type']!='building':shapes.append(f'<text x="620" y="{y+5}">{esc(p["value"])}</text>')
 return '<figure>'+caption+f'<svg role="img" aria-label="{esc(f["title"])}" viewBox="0 0 760 {height}" xmlns="http://www.w3.org/2000/svg"><style>text{{font:15px sans-serif;fill:#16263f}}</style>'+''.join(shapes)+f'</svg><small>{esc(f.get("note",""))}</small></figure>'
def render_contract(path,out,branding=None):
 c=check_contract(path);out=Path(out);out.mkdir(parents=True,exist_ok=True)
 if (out/'report.html').exists():raise ValueError('OUTPUT_EXISTS_USE_NEW_VERSION')
 brand=load(branding) if branding else {}
 values={q['id']:q['value'] for q in c['claims']}
 figs={f['id']:{**f,'title':bound_text(f['title'],values),'note':bound_text(f.get('note',''),values),'points':[{**p,'label':bound_text(p['label'],values)} for p in f['points']]} for f in c.get('figures',[])}
 title=bound_text(c['title'],values) if c.get('title') else c['question'];body=''
 for b in c['blocks']:
  ps=[]
  for p in b['paragraphs']:
   rendered=bound_text(p,values);text=esc(rendered)
   for h in sorted(b.get('highlights',[]),key=len,reverse=True):
    if h in rendered:text=text.replace(esc(h),'<mark>'+esc(h)+'</mark>')
   ps.append('<p>'+text+'</p>')
  external=''
  for a in c.get('assets',[]):
   if a['id'] not in b.get('asset_ids',[]):continue
   import base64
   ap=(Path(path).resolve().parent/a['file']).resolve();mime='image/png' if ap.suffix=='.png' else 'image/svg+xml'
   external+='<figure><img style="width:100%;height:auto" alt="'+esc(bound_text(a['alt'],values))+'" src="data:'+mime+';base64,'+base64.b64encode(ap.read_bytes()).decode()+'"><figcaption>'+esc(bound_text(a['caption'],values))+'</figcaption>'
   if a['kind']=='chart':external+='<table>'+''.join('<tr><th>'+esc(bound_text(pt['label'],values))+'</th><td>'+esc(values[pt['claim_id']])+' '+esc(a['unit'])+'</td></tr>' for pt in a['points'])+'</table>'
   external+='</figure>'
  body+=f'<section data-block-id="{esc(b["id"])}"><h2>{esc(bound_text(b["title"],values))}</h2>'+''.join(ps)+''.join(fig_html(figs[i]) for i in b.get('figure_ids',[]))+external+'</section>'
 logo=''
 if brand.get('logo'):
  import base64
  p=(Path(branding).resolve().parent/brand['logo']).resolve();mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'}.get(p.suffix.lower())
  if not mime or p.stat().st_size>2_000_000:raise ValueError('LOGO_PNG_JPEG_MAX_2MB')
  logo=f'<img alt="상호 로고" style="max-width:120px;max-height:60px" src="data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"/>'
 mode={'actual':'','historical_replay':'과거 자료 재생 사례 · 현재 매물 안내가 아닙니다.','synthetic_test':'합성 검증 예시 · 실제 시세가 아닙니다.'}[c['mode']]
 css=(ROOT/'assets/report.css').read_text(encoding='utf-8')
 doc='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+css+'</style></head><body><main><header>'+logo+'<small>'+esc(brand.get('business_name') or 'EZIWORK')+'</small><h1>'+esc(title)+'</h1><p>'+esc(c['question'])+'</p><p>'+esc(mode)+' 기준일 '+esc(c['basis_date'])+'</p><p>'+esc(c['scope'])+'</p></header>'+body+'<footer><h2>출처</h2>'+''.join('<p>'+esc(s['title'])+' · '+esc(s['basis_date'])+(' · <a href="'+esc(s['url'])+'">원문</a>' if s['url'].startswith('http') else ' · 사용자 제공 정리표')+'</p>' for s in c['sources'])+'<p>'+esc(' · '.join(str(brand.get(k,'')) for k in ['business_name','contact_name','phone'] if brand.get(k)))+'</p></footer></main></body></html>'
 if c.get('cover',{}).get('enabled',True):doc=covers.wrap_document(doc,cover_metadata(c),brand)
 (out/'report.html').write_text(doc,encoding='utf-8')
 save(out/'render-manifest.json',{'contract_sha256':sha(path),'dataset_sha256':c['dataset_sha256'],'html_sha256':sha(out/'report.html'),'mode':c['mode'],'semantic_review':'CODEX_ATTESTED_NOT_AUTOMATICALLY_PROVEN','blocks':len(c['blocks'])})
 return out/'report.html'

def cover_metadata(c):
 values={q['id']:q['value'] for q in c['claims']}
 kind=next(r['report_type'] for r in load(ROOT/'references/report-types.json')['reports'] if r['report_id']==c['report_id'])
 meta={'report_id':c['report_id'],'mode':c['mode'],'basis_date':c['basis_date'],'title':bound_text(c['title'],values) if c.get('title') else kind}
 for field in covers.FIELDS:
  if field in c.get('cover',{}):meta[field]=bound_text(c['cover'][field],values)
 return meta
def output_environment():
 try:
  proc=subprocess.run([node(),str(ROOT/'scripts/render.mjs'),'--doctor'],capture_output=True,text=True,encoding='utf-8')
  renderer=json.loads(proc.stdout) if proc.returncode==0 else {'status':'DEPENDENCIES_REQUIRED'}
 except (OSError,ValueError):renderer={'status':'DEPENDENCIES_REQUIRED'}
 integration=integrations.check()
 return {'ready':bool(renderer.get('browser_found') and integration['ready']), 'renderer':renderer,'integrations_ready':integration['ready']}

def produce_pdf(html_path,pdf_path,contract=None):
 from delivery import file_hash,seal_output
 before=file_hash(html_path);contract_hash=file_hash(contract) if contract else None
 run=subprocess.run([node(),str(ROOT/'scripts/render.mjs'),'--input',str(html_path),'--output',str(pdf_path)],capture_output=True,text=True,encoding='utf-8')
 if run.returncode:
  if 'PLAYWRIGHT_REQUIRED' in run.stdout:raise ValueError('PLAYWRIGHT_REQUIRED_RUN_NPM_CI')
  raise ValueError('PDF_RENDER_FAILED_CHECK_ASSETS_LAYOUT_AND_OUTPUT_PATH')
 return seal_output(html_path,pdf_path,contract,before,contract_hash)

def main():
 p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,default=Path.cwd()/'eziwork-output');sub=p.add_subparsers(dest='cmd',required=True)
 sub.add_parser('doctor');sub.add_parser('catalog')
 a=sub.add_parser('key-env');a.add_argument('action',choices=['check','setup','ensure','window']);a.add_argument('--name',choices=key_environment.BASIC);a.add_argument('--replace',action='store_true')
 a=sub.add_parser('integrations');a.add_argument('action',choices=['check','setup']);a.add_argument('--python',action='store_true',dest='install_python')
 a=sub.add_parser('map');a.add_argument('--request',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
 a=sub.add_parser('chart');a.add_argument('--spec',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
 a=sub.add_parser('configure');a.add_argument('--name',required=True,choices=ALLOWED)
 a=sub.add_parser('privacy-check');a.add_argument('--file',type=Path,required=True)
 for n in ['preflight','collect','import','status']:
  a=sub.add_parser(n)
  if n!='status':a.add_argument('--request',type=Path,required=True)
  if n!='preflight':a.add_argument('--run-id',required=True)
  if n=='collect':a.add_argument('--resume',action='store_true');a.add_argument('--force-refresh',action='store_true')
  if n=='import':a.add_argument('--file',type=Path,required=True);a.add_argument('--privacy-reviewed',action='store_true')
 a=sub.add_parser('prepare');a.add_argument('--run-id',required=True);a.add_argument('--report',required=True);a.add_argument('--review',type=Path)
 for n in ['verify','render']:
  a=sub.add_parser(n);a.add_argument('--contract',type=Path,required=True)
  if n=='render':a.add_argument('--output',type=Path,required=True);a.add_argument('--branding',type=Path);a.add_argument('--pdf',action='store_true')
 a=sub.add_parser('official-document');a.add_argument('--file',type=Path,required=True);a.add_argument('--url',required=True);a.add_argument('--output',type=Path,required=True)
 a=sub.add_parser('catchment');a.add_argument('--spec',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
 a=sub.add_parser('pdf');a.add_argument('--input',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--contract',type=Path)
 a=sub.add_parser('delivery-check');a.add_argument('--html',type=Path,required=True);a.add_argument('--pdf',type=Path,required=True);a.add_argument('--contract',type=Path)
 a=sub.add_parser('cover');a.add_argument('--input',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--contract',type=Path,required=True);a.add_argument('--branding',type=Path)
 a=sub.add_parser('report-job');a.add_argument('action',choices=['start','status','bind','finish']);a.add_argument('--job',type=Path,required=True);a.add_argument('--request',type=Path);a.add_argument('--mode',choices=['actual','historical_replay','synthetic_test'],default='actual');a.add_argument('--contract',type=Path);a.add_argument('--html',type=Path);a.add_argument('--pdf',type=Path);a.add_argument('--reviewed',action='store_true')
 args=p.parse_args()
 # Before file-credential injection: local files must not appear to be OS variables.
 if args.cmd in ('key-env','configure'):
  try:
   if args.cmd=='configure':result=key_environment.setup(args.name,replace=True)
   else:
    if args.action in ('check','ensure') and (args.name or args.replace):raise ValueError('OPTIONS_REQUIRE_SETUP_OR_WINDOW')
    if args.action=='check':result=key_environment.check()
    elif args.action=='setup':result=key_environment.setup(args.name,replace=args.replace)
    elif args.action=='ensure':result=key_environment.ensure()
    else:
     from key_window import open_window
     result=open_window(args.name,args.replace)
   print(json.dumps(result,ensure_ascii=False,indent=2));return 2 if result.get('missing') or result.get('input_cancelled') or result.get('window_opened') else 0
  except (KeyboardInterrupt,EOFError):
   print(json.dumps({'status':'INPUT_CANCELLED','live_call':False}));return 2
  except (ValueError,OSError) as ex:
   code=str(ex) if isinstance(ex,ValueError) else 'KEY_STORE_WRITE_OR_READ_FAILED'
   print(json.dumps({'status':'KEY_ENV_ACTION_REQUIRED','code':code,'guide':'references/api-setup.md','live_call':False}));return 2
 if args.cmd=='report-job':
  import report_job
  try:
   if args.action=='start':
    if not args.request:raise ValueError('REQUEST_REQUIRED')
    result=report_job.start(args.request,args.job,args.mode)
   else:result=report_job.status(args.job)
   job=report_job.current(args.job)
   if job['mode']=='actual':
    state=key_environment.ensure() if args.action=='start' else key_environment.check()
    if state.get('missing') or state.get('window_opened'):
     print(json.dumps({'status':'CREDENTIALS_REQUIRED','complete':False,'job':str(args.job),'onboarding':state,'next_action':'Complete input, then run report-job status for this job.'},ensure_ascii=False));return 2
   if args.action=='bind':
    if not args.contract:raise ValueError('CONTRACT_REQUIRED')
    result=report_job.bind(args.job,args.contract,check_contract(args.contract))
   elif args.action=='finish':
    if not args.html or not args.pdf:raise ValueError('HTML_AND_PDF_REQUIRED')
    if job.get('contract'):check_contract(job['contract'])
    result=report_job.finish(args.job,args.html,args.pdf,args.reviewed)
   elif job.get('contract') and Path(job['contract']).is_file() and sha(job['contract'])==job.get('contract_sha256'):
    check_contract(job['contract'])
   if args.action in ('start','status') and not result.get('complete'):
    readiness=output_environment()
    if not readiness['ready']:result.update(status='DEPENDENCIES_REQUIRED',environment=readiness,next_action='Run integrations setup --python, npm ci in the skill folder, then report-job status.')
   print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('complete') else 2
  except (ValueError,OSError,KeyError,TypeError,CollectionError) as ex:
   code=ex.code if isinstance(ex,CollectionError) else str(ex) if isinstance(ex,ValueError) else 'JOB_INPUT_OR_FILE_REQUIRED'
   print(json.dumps({'status':'ACTION_REQUIRED','complete':False,'code':code,'guide':'references/report-jobs.md'},ensure_ascii=False));return 2
 # Inspect registration before credentials from local files are injected.
 needs_keys=args.cmd in ('preflight','collect','prepare','map')
 if args.cmd=='render':
  needs_keys=load(args.contract).get('mode')=='actual'
 if args.cmd=='import':
  needs_keys=load(args.file).get('evidence_mode')=='ACTUAL'
 if needs_keys:
  try:blocked=key_environment.require_registered()
  except (OSError,ValueError):
   print(json.dumps({'status':'KEY_STORE_REVIEW_REQUIRED','live_call':False}));return 2
  if blocked:
   print(json.dumps(blocked,ensure_ascii=False,indent=2));return 2
 registration_state=key_environment.check() if args.cmd=='doctor' else None
 with environment() as redact:
  try:
   if args.cmd=='integrations':
    if args.action=='check' and args.install_python:raise ValueError('PYTHON_INSTALL_REQUIRES_SETUP')
    result=integrations.setup(install_python=args.install_python) if args.action=='setup' else integrations.check()
   elif args.cmd=='map':result=integrations.map_collect(load(args.request),args.output,credentials().get('VWORLD_API_KEY',''))
   elif args.cmd=='chart':
    from scientific_charts import chart
    spec=load(args.spec);spec['dataset']=str((args.spec.resolve().parent/spec['dataset']).resolve());result=chart(spec,args.output)
   elif args.cmd=='cover':
    c=check_contract(args.contract)
    if args.output.exists():raise ValueError('OUTPUT_EXISTS_USE_NEW_VERSION')
    if args.input.resolve().parent!=args.output.resolve().parent:raise ValueError('KEEP_CUSTOM_HTML_ASSET_BASE_USE_SAME_FOLDER')
    document=covers.wrap_document(args.input.read_text(encoding='utf-8-sig'),cover_metadata(c),load(args.branding) if args.branding else {})
    args.output.write_text(document,encoding='utf-8');result={'status':'V_COVERS_ADDED','output':str(args.output),'body_review':'REQUIRES_CODEX_COMPARISON_TO_CONTRACT'}
   elif args.cmd=='doctor':
    try:nd=node()
    except ValueError:nd=None
    result={'os':platform.system(),'python':platform.python_version(),'node_found':bool(nd),'credential_presence':{k:bool(os.environ.get(k)) for k in ALLOWED},'browser_workflow':'REQUIRES_CONNECTED_CODEX_BROWSER','mac_actual_validation':'SEE qa/release-status.json'}
    try:result['pypdf']=version('pypdf')
    except PackageNotFoundError:result['pypdf']='INSTALL_REQUIREMENTS'
    fonts=[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/malgun.ttf',Path('/System/Library/Fonts/AppleSDGothicNeo.ttc'),Path('/System/Library/Fonts/Supplemental/AppleGothic.ttf')]
    result['korean_os_font_found']=any(f.is_file() for f in fonts)
    result['python_supported']=sys.version_info>=(3,11)
    result['key_registration']=registration_state
    result['geometry_libraries']={}
    for lib,wanted in [('shapely','2.1.2'),('pyproj','3.7.2')]:
     try:installed=version(lib)
     except PackageNotFoundError:installed=None
     result['geometry_libraries'][lib]={'installed':installed,'expected':wanted,'match':installed==wanted}
    result['integrations']=integrations.check()
    if nd:
     check=subprocess.run([nd,str(ROOT/'scripts/render.mjs'),'--doctor'],capture_output=True,text=True,encoding='utf-8');result['renderer']=json.loads(check.stdout) if check.returncode==0 else {'status':'DEPENDENCIES_REQUIRED'}
   elif args.cmd=='official-document':
    from public_evidence import public_document
    result=public_document(args.file,args.url,args.output)
   elif args.cmd=='catchment':
    from public_evidence import catchment
    if args.output.exists():raise ValueError('OUTPUT_EXISTS_USE_NEW_VERSION')
    result=catchment(load(args.spec),args.spec.parent);save(args.output,result)
   elif args.cmd=='catalog':result=load(ROOT/'references/report-types.json')
   elif args.cmd=='privacy-check':result={'signals':privacy_issues(args.file),'manual_review_required':True,'guarantee':False}
   elif args.cmd in ['preflight','collect','import','status']:
    if args.cmd=='import':
     if not args.privacy_reviewed:raise ValueError('PRIVACY_REVIEW_REQUIRED')
     payload=load(args.file)
     official=payload.get('intake_channel')=='OFFICIAL_PUBLIC' and payload.get('source_id') in ('S07','S12','S17')
     if official:
      from public_evidence import review_official_payload
      review_official_payload(payload,args.file.parent,load(args.request))
     issues=[] if official else privacy_issues(args.file)
     # Attachments must also pass the scan before the collector copies originals.
     def scan_files(x):
      if isinstance(x,dict):
       for k,v in x.items():
        if k in ['file','file_path','path'] and isinstance(v,str):
         f=(args.file.parent/v).resolve()
         if f.is_file():issues.extend(privacy_issues(f))
        else:scan_files(v)
      elif isinstance(x,list):
       for v in x:scan_files(v)
     if not official:scan_files(payload)
     for rel in payload.get('observation',{}).get('evidence_files',[]):
      f=(args.file.parent/rel).resolve()
      if f.is_file() and f.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):issues.extend(privacy_issues(f))
     if issues:raise ValueError('PERSONAL_DATA_OR_UNREVIEWED_FORMAT: '+','.join(sorted(set(issues))))
    cli=['collector','--output',str(args.workspace/'runs'),'--cache',str(args.workspace/'cache'),args.cmd]
    if args.cmd!='status':cli+=['--request',str(args.request)]
    if args.cmd!='preflight':cli+=['--run-id',args.run_id]
    if args.cmd=='collect':
     if args.resume:cli+=['--resume']
     if args.force_refresh:cli+=['--force-refresh']
    if args.cmd=='import':cli+=['--file',str(args.file)]
    prior=sys.argv;sys.argv=cli
    try:
     code=collector.main()
     if code==0 and args.cmd in ['collect','import']:
      m=load(args.workspace/'runs'/args.run_id/'manifest.json')
      if any(not s.get('complete') for s in m.get('sources',{}).values()):return 2
     return code
    finally:sys.argv=prior
   elif args.cmd=='prepare':
    from prepare_report_evidence import prepare,review_coverage
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',args.run_id):raise ValueError('RUN_ID')
    run=args.workspace/'runs'/args.run_id
    if args.review:review_coverage(run,args.review)
    dest=prepare(run,args.report);result={'dataset':str(dest),'sha256':sha(dest)}
   elif args.cmd=='verify':c=check_contract(args.contract);result={'status':'PASS','report_id':c['report_id'],'mode':c['mode'],'semantic_review':'CODEX_ATTESTED'}
   elif args.cmd=='render':
    dest=render_contract(args.contract,args.output,args.branding)
    if args.pdf:result=produce_pdf(dest,args.output/'report.pdf',args.contract)
    else:result={'status':'HTML_ONLY','html':str(dest),'pdf':None}
   elif args.cmd=='pdf':
    if args.contract:check_contract(args.contract)
    result=produce_pdf(args.input,args.output,args.contract)
   elif args.cmd=='delivery-check':
    from delivery import check_delivery,check_receipt
    result=check_receipt(args.html,args.pdf,args.contract) if args.contract else check_delivery(args.html,args.pdf)
   print(json.dumps(redact.data(result),ensure_ascii=False,indent=2))
   if args.cmd=='doctor' and not (result['integrations']['ready'] and result.get('renderer',{}).get('browser_found')):return 2
   if args.cmd=='map' and result.get('status')!='PASS':return 2
   if args.cmd=='integrations' and not result.get('ready'):return 2
   return 0
  except (CollectionError,OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError) as ex:
   code=ex.code if isinstance(ex,CollectionError) else (str(ex) if isinstance(ex,ValueError) else 'LOCAL_INPUT_OR_RUNTIME_ERROR')
   print(json.dumps(redact.data({'status':'ACTION_REQUIRED','code':code,'guide':'references/workflow.md' if args.cmd in ('render','pdf','delivery-check') else 'references/api-setup.md'}),ensure_ascii=False));return 2
if __name__=='__main__':
 if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
 raise SystemExit(main())
