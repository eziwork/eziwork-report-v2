"""Pinned upstream integrations. Check is offline; setup alone downloads tools."""
from pathlib import Path
import hashlib, json, os, platform, re, subprocess, sys, tempfile, time, urllib.request
from importlib.metadata import version, PackageNotFoundError
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
def load(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):
 from collector import write as atomic_write
 atomic_write(Path(p),data)
def lock():return load(ROOT/'references/integrations-lock.json')
def runtime():return Path(os.environ.get('EZIWORK_RUNTIME_DIR',ROOT/'runtime'))
def binary():return runtime()/('vworld.exe' if platform.system()=='Windows' else 'vworld')
def font():
 explicit=os.environ.get('EZIWORK_KOREAN_FONT')
 paths=[Path(explicit)] if explicit else []
 paths += [Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/malgun.ttf',Path('/System/Library/Fonts/AppleSDGothicNeo.ttc'),Path('/System/Library/Fonts/Supplemental/AppleGothic.ttf')]
 paths += list(Path('/usr/share/fonts').glob('**/*NotoSansCJK*.ttc'))
 return next((p for p in paths if p.is_file()),None)
def check():
 cfg=lock();bad=[]
 for name,s in cfg['skills'].items():
  for rel,digest in s['files'].items():
   p=ROOT/'vendor'/name/rel
   if not p.is_file() or sha(p)!=digest:bad.append(name+'/'+rel)
 libs={}
 for name,want in [('matplotlib','3.10.7'),('Pillow','12.3.0'),('pypdf','6.10.0')]:
  try:got=version(name)
  except PackageNotFoundError:got=None
  libs[name]={'required':want,'found':got,'match':got==want}
 asset=cfg['vworld_release']['assets'].get(platform.system());exe=binary()
 ok=bool(asset and exe.is_file() and sha(exe)==asset['sha256'])
 return {'version':'2.2.0','network_called':False,'vendor_integrity':'PASS' if not bad else 'FAIL','changed_files':bad,'vworld':{'version':'0.3.5','verified':ok},'libraries':libs,'korean_font_found':bool(font()),'ready':not bad and ok and all(v['match'] for v in libs.values()) and bool(font())}
def setup(install_python=False):
 if install_python:
  target=runtime()/'python';target.mkdir(parents=True,exist_ok=True)
  result=subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--target',str(target),'-r',str(ROOT/'requirements.txt')],capture_output=True,text=True,encoding='utf-8',errors='replace')
  if result.returncode:raise ValueError('PYTHON_DEPENDENCY_INSTALL_FAILED')
  sys.path.insert(0,str(target))
 asset=lock()['vworld_release']['assets'].get(platform.system())
 if not asset:raise ValueError('VWORLD_OS_UNSUPPORTED')
 dest=binary();dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.is_file() and sha(dest)==asset['sha256']:
  result=check();result['network_called']=install_python;result['api_called']=False;return result
 req=urllib.request.Request(asset['url'],headers={'User-Agent':'eziwork-report-v2/2.2.0'})
 with urllib.request.urlopen(req,timeout=120) as r:raw=r.read(150_000_001)
 if len(raw)>150_000_000 or hashlib.sha256(raw).hexdigest()!=asset['sha256']:raise ValueError('VWORLD_CHECKSUM_MISMATCH')
 fd,temp=tempfile.mkstemp(prefix='vworld-',dir=dest.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(raw)
  Path(temp).chmod(0o700)
  for attempt in range(3):
   try:os.replace(temp,dest);break
   except PermissionError:
    if attempt==2:raise
    time.sleep(.2*(attempt+1))
 finally:Path(temp).unlink(missing_ok=True)
 result=check();result['network_called']=True;result['api_called']=False;return result
def classify(text):
 t=text.upper()
 if any(x in t for x in ['INVALID_KEY','INCORRECT_KEY','UNREGISTERED_KEY','401','403','인증']):return 'AUTH_REJECTED'
 if any(x in t for x in ['429','LIMIT','QUOTA']):return 'RATE_LIMIT'
 if any(x in t for x in ['TIMEOUT','TIMED OUT','502','503','504','CONNECT']):return 'TEMPORARY_FAILURE'
 if any(x in t for x in ['NOT_FOUND','NOT FOUND','ZERO_RESULT']):return 'NO_RESULT'
 if any(x in t for x in ['INVALID_REQUEST','INVALID_RANGE','PARAM_REQUIRED','CONFIG']):return 'CONFIG_ERROR'
 return 'UNCLASSIFIED_FAILURE'
def cli(args,key):
 if not key:raise ValueError('VWORLD_KEY_MISSING')
 asset=lock()['vworld_release']['assets'].get(platform.system())
 if not asset or not binary().is_file() or sha(binary())!=asset['sha256']:raise ValueError('VWORLD_SETUP_REQUIRED')
 # Key is only in a short-lived private configuration, never an argv value.
 with tempfile.TemporaryDirectory(prefix='eziwork-vworld-') as d:
  p=Path(d)/'config.toml';p.write_text('[[keys]]\nkey = '+json.dumps(key)+'\n',encoding='utf-8');p.chmod(0o600)
  env={**os.environ,'VWORLD_NO_UPDATE_CHECK':'1','RUST_LOG':'off'}
  command=[str(binary()),'--config',str(p),'--pretty']
  if os.environ.get('VWORLD_DOMAIN'):command+=['--referer',os.environ['VWORLD_DOMAIN']]
  for attempt in range(3):
   try:
    r=subprocess.run(command+list(args),capture_output=True,text=True,encoding='utf-8',errors='replace',env=env,timeout=60)
    if r.returncode==0:return r.stdout.replace(key,'[REDACTED]')
    code=classify(r.stdout+r.stderr)
   except subprocess.TimeoutExpired:code='TEMPORARY_FAILURE'
   if code not in ['RATE_LIMIT','TEMPORARY_FAILURE'] or attempt==2:raise ValueError('VWORLD_'+code)
   time.sleep(1+attempt)
def match_address(response,expected):
 if 'ok' in response:
  if response.get('ok') is not True:raise ValueError('VWORLD_NO_RESULT')
  response=response.get('result',{})
 r=response.get('response',response)
 if r.get('status') not in (None,'OK'):raise ValueError('VWORLD_'+classify(json.dumps(r,ensure_ascii=False)))
 result=r.get('result')
 if not result:raise ValueError('VWORLD_NO_RESULT')
 if isinstance(result,list):raise ValueError('VWORLD_AMBIGUOUS_CANDIDATES')
 text=json.dumps(r.get('refined',{}),ensure_ascii=False)
 compact=lambda s:re.sub(r'\s+','',s)
 if not expected or any((not re.search(r'(?<![\d-])'+re.escape(x)+r'(?![\d-])',text)) if re.fullmatch(r'\d+(?:-\d+)?',x) else compact(x) not in compact(text) for x in expected):raise ValueError('VWORLD_TARGET_MISMATCH')
 point=result.get('point',{});x=float(point['x']);y=float(point['y'])
 if not (124<x<132 and 33<y<39):raise ValueError('VWORLD_COORDINATE_RANGE')
 return x,y
def map_collect(request,output,key):
 out=Path(output)
 if out.exists():raise ValueError('OUTPUT_EXISTS_USE_NEW_VERSION')
 out.mkdir(parents=True);calls=[];points=[];now=datetime.now(timezone.utc).isoformat()
 try:
  targets=request['targets']
  if not 1<=len(targets)<=4:raise ValueError('MAP_TARGET_COUNT')
  for i,t in enumerate(targets):
   raw=cli(['geocode',t['address'],'--type',t.get('type','ROAD')],key)
   payload=json.loads(raw);write(out/f'geocode-{i+1}.json',payload)
   x,y=match_address(payload,t['expected_tokens']);points.append({'label':t['label'],'address':t['address'],'lon':x,'lat':y,'location_kind':'address_lookup_point'})
   calls.append({'command':'geocode','address':t['address'],'status':'PASS'})
  center=[sum(p[k] for p in points)/len(points) for k in ['lon','lat']]
  dest=out/'map-base.png';zoom=int(request.get('zoom',16))
  if not 6<=zoom<=18:raise ValueError('MAP_ZOOM_RANGE')
  cli(['staticmap',','.join(map(str,center)),'--zoom',str(zoom),'--size','1024,768','--basemap','GRAPHIC','-o',str(dest)],key)
  from PIL import Image
  with Image.open(dest) as im:
   if im.format!='PNG' or im.size!=(1024,768):raise ValueError('MAP_INVALID_IMAGE')
   im.verify()
  calls.append({'command':'staticmap','status':'PASS'})
  result={'status':'PASS','skill':'vworld','version':'0.3.5','execution':'upstream_cli','queried_at':now,'input_sha256':hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'points':points,'center':center,'zoom':zoom,'source':'VWorld','map_sha256':sha(dest),'scope':'address_and_background_only','calls':calls}
 except (ValueError,KeyError,OSError,json.JSONDecodeError) as e:
  result={'status':'HOLD','code':str(e) if isinstance(e,ValueError) else 'MAP_RESPONSE_INVALID','queried_at':now,'calls':calls}
 write(out/'map-provenance.json',result)
 return result

def verify_asset(asset,base,claims):
 """External chart/map assets are accepted only with linked evidence and review."""
 p=(Path(base)/asset['file']).resolve()
 if p.suffix.lower() not in ('.png','.svg') or not p.is_file() or sha(p)!=asset['sha256']:raise ValueError('ASSET_CHANGED')
 prov=(Path(base)/asset['provenance']).resolve()
 if not prov.is_file() or sha(prov)!=asset['provenance_sha256']:raise ValueError('ASSET_PROVENANCE_CHANGED')
 record=load(prov)
 if record.get('status')!='PASS':raise ValueError('ASSET_NOT_READY')
 if asset['kind']=='chart':
  expected=[{'label':x['label'],'value':claims[x['claim_id']]} for x in asset['points']]
  if record.get('points')!=expected or record.get('unit')!=asset['unit']:raise ValueError('ASSET_DATA_MISMATCH')
  if record.get('output_sha256',{}).get(p.suffix[1:])!=sha(p):raise ValueError('ASSET_OUTPUT_MISMATCH')
 elif asset['kind']=='map':
  if record.get('map_sha256')!=sha(p) or asset.get('address_review')!='PASS':raise ValueError('MAP_REVIEW_REQUIRED')
  if not record.get('queried_at') or record.get('scope')!='address_and_background_only' or record.get('execution')!='upstream_cli' or not record.get('input_sha256') or not record.get('points'):raise ValueError('MAP_PROVENANCE_INCOMPLETE')
  for point in record['points']:
   if not point.get('address') or not point.get('label') or point.get('location_kind')!='address_lookup_point':raise ValueError('MAP_TARGET_REQUIRED')
   if not (124<float(point['lon'])<132 and 33<float(point['lat'])<39):raise ValueError('MAP_COORDINATE_RANGE')
 else:raise ValueError('ASSET_KIND')
 if not asset.get('alt') or not asset.get('caption'):raise ValueError('ASSET_DESCRIPTION_REQUIRED')
 return p
