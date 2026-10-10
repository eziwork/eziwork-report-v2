"""Official file intake and VWorld address/catchment tools; no school/law API."""
import csv
import datetime as D
import hashlib
import json
from pathlib import Path
import re
import sys
from html.parser import HTMLParser
from adapters import CollectionError
from evidence_rules import official_url,digest_file,public_issues

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,data):
    from collector import write as atomic
    atomic(p,data)

def extract(path):
    path=Path(path)
    if path.stat().st_size>30_000_000:raise CollectionError('OFFICIAL_FILE_TOO_LARGE')
    if path.suffix.lower()=='.pdf':
        from pypdf import PdfReader
        text='\n'.join(p.extract_text() or '' for p in PdfReader(path).pages)
    elif path.suffix.lower() in ('.txt','.csv','.json','.geojson','.html','.htm'):
        try:text=path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:text=path.read_text(encoding='cp949')
        if path.suffix.lower() in ('.html','.htm'):
            class Text(HTMLParser):
                def __init__(self):super().__init__();self.parts=[];self.skip=0
                def handle_starttag(self,t,a):
                    if t in ('script','style'):self.skip+=1
                def handle_endtag(self,t):
                    if t in ('script','style'):self.skip=max(0,self.skip-1)
                def handle_data(self,d):
                    if not self.skip:self.parts.append(d)
            parser=Text();parser.feed(text);text='\n'.join(parser.parts)
    else:raise CollectionError('UNSUPPORTED_FORMAT_USE_OFFICIAL_PDF_CSV_JSON_OR_GEOJSON')
    if not text.strip():raise CollectionError('EXTRACTION_EMPTY_MANUAL_TRANSCRIPTION_REQUIRED')
    return text

def public_document(path,url,output):
    if not official_url(url):raise CollectionError('OFFICIAL_ORIGIN_REQUIRED')
    text=extract(path);out=Path(output)
    if out.exists():raise CollectionError('OUTPUT_EXISTS_USE_NEW_VERSION')
    out.mkdir(parents=True)
    (out/'extracted.txt').write_text(text,encoding='utf-8')
    result={'status':'EXTRACTED_REVIEW_REQUIRED','source_url':url,'raw_sha256':digest_file(path),
        'source_file':str(Path(path).resolve()),'extracted_sha256':digest_file(out/'extracted.txt'),
        'observed_at':D.datetime.now(D.timezone.utc).isoformat(),
        'review_required':['원문 대상·기준일·필드 대조','공식 공개 연락처 범위 확인','고객 개인정보 혼입 확인']}
    write(out/'document.json',result);return result

def review_official_payload(payload,base,request):
    if payload.get('intake_channel')!='OFFICIAL_PUBLIC':raise CollectionError('OFFICIAL_INTAKE_REQUIRED')
    if not official_url(payload.get('source_url')):raise CollectionError('OFFICIAL_ORIGIN_REQUIRED')
    if payload.get('data_format_version')!=2:raise CollectionError('INPUT_FORMAT_MIGRATION_REQUIRED')
    if not payload.get('attachments') or not payload.get('records'):raise CollectionError('OFFICIAL_ORIGINAL_REQUIRED')
    texts=[];hashes=set()
    for attachment in payload['attachments']:
        path=(base/attachment.get('file','')).resolve()
        if not path.is_relative_to(base.resolve()) or not path.is_file():raise CollectionError('OFFICIAL_ORIGINAL_MISSING')
        if not official_url(attachment.get('source_url')):raise CollectionError('OFFICIAL_ATTACHMENT_ORIGIN_REQUIRED')
        sha=digest_file(path)
        if sha!=attachment.get('sha256'):raise CollectionError('OFFICIAL_ORIGINAL_HASH_MISMATCH')
        hashes.add(sha);texts.append((sha,extract(path)))
    # Only exactly reviewed institution contacts in the matched original are exempted.
    for sha,text in texts:
        if re.search(r'\b\d{6}\s*[- ]?\s*[1-8]\d{6}\b',text):raise CollectionError('PERSONAL_ID_IN_OFFICIAL_INPUT')
        for contact in payload.get('public_contact_review',[]):
            if contact.get('raw_sha256')!=sha:continue
            if contact.get('institutional_public_contact') is not True or not contact.get('review_note'):
                raise CollectionError('PUBLIC_CONTACT_REVIEW_REQUIRED')
            exact=contact.get('value','')
            if not exact or exact not in text or not re.fullmatch(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|0\d{1,2}[- ]\d{3,4}[- ]\d{4}',exact):raise CollectionError('PUBLIC_CONTACT_NOT_IN_ORIGINAL')
            text=text.replace(exact,'[PUBLIC_INSTITUTION_CONTACT]')
        if re.search(r'\b\d{6}\s*[- ]?\s*[1-8]\d{6}\b|(?<!\d)01[016789][ -]?\d{3,4}[ -]?\d{4}(?!\d)|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text):
            raise CollectionError('PERSONAL_DATA_OR_UNREVIEWED_PUBLIC_CONTACT')
    for row in payload['records']:
        proof=row.get('original_proof',{})
        if proof.get('raw_sha256') not in hashes or not proof.get('field_quotes') or proof.get('review_status')!='VERIFIED':
            raise CollectionError('ROW_ORIGINAL_REVIEW_REQUIRED')
        original=next(text for sha,text in texts if sha==proof['raw_sha256'])
        required={'S07':['road_address','parcel_address'],'S12':['school_code','address'],'S17':['law_name','article','law_body','effective_date']}[payload['source_id']]
        for field in required:
            quote=proof['field_quotes'].get(field)
            matched=str(row.get(field,'')) in str(quote)
            if field=='effective_date' and quote:
                dates=re.findall(r'(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})',quote)
                matched=any(f'{int(y):04}-{int(m):02}-{int(d):02}'==row.get(field) for y,m,d in dates)
            if not quote or quote not in original or not matched:
                raise CollectionError('FIELD_ORIGINAL_MISMATCH:'+field)
        if row.get('record_type')=='assignment':
            if row.get('notice_sha256') not in hashes:raise CollectionError('FINAL_NOTICE_ORIGINAL_REQUIRED')
            spec=payload.get('catchment_spec')
            if not spec:raise CollectionError('CATCHMENT_GEOMETRY_REQUIRED')
            if any(spec.get(k) not in hashes for k in ('geometry_sha256','join_sha256')):
                raise CollectionError('CATCHMENT_ORIGINAL_ATTACHMENTS_REQUIRED')
            if spec.get('target_id')!=request['target']['subject_id']:raise CollectionError('CATCHMENT_TARGET_MISMATCH')
            target=request['target']
            if any(target.get(k) is None or float(target[k])!=float(spec[k]) for k in ('lon','lat')):
                raise CollectionError('CATCHMENT_TARGET_COORDINATE_PROOF_REQUIRED')
            row['geometry_result']=catchment(spec,base)

def catchment(spec,base):
    from shapely.geometry import shape,Point
    from shapely.ops import transform
    from pyproj import CRS,Transformer
    geometry=(Path(base)/spec['geometry_file']).resolve();join=(Path(base)/spec['join_file']).resolve()
    if not geometry.is_relative_to(Path(base).resolve()) or not join.is_relative_to(Path(base).resolve()):
        raise CollectionError('GEOMETRY_PATH_OUTSIDE_INPUT')
    if digest_file(geometry)!=spec['geometry_sha256'] or digest_file(join)!=spec['join_sha256']:raise CollectionError('GEOMETRY_HASH_MISMATCH')
    if not official_url(spec.get('source_url')) or not spec.get('basis_date'):raise CollectionError('GEOMETRY_OFFICIAL_SOURCE_REQUIRED')
    geo=load(geometry);links=load(join)
    crs=CRS.from_user_input(spec['source_crs']);to_metric=Transformer.from_crs(crs,'EPSG:5179',always_xy=True).transform
    point=Point(*Transformer.from_crs('EPSG:4326','EPSG:5179',always_xy=True).transform(float(spec['lon']),float(spec['lat'])))
    if not (124<float(spec['lon'])<132 and 33<float(spec['lat'])<39):raise CollectionError('GEOMETRY_TARGET_RANGE')
    matched=[];boundary=False
    for f in geo.get('features',[]):
        g=shape(f['geometry'])
        if g.geom_type not in ('Polygon','MultiPolygon') or g.is_empty or not g.is_valid:raise CollectionError('INVALID_CATCHMENT_GEOMETRY')
        native_point=Point(*Transformer.from_crs('EPSG:4326',crs,always_xy=True).transform(float(spec['lon']),float(spec['lat'])))
        inside=g.covers(native_point)
        native_boundary=g.boundary.distance(native_point)<=1e-9
        if crs.is_geographic:g=g.segmentize(0.001)
        g=transform(to_metric,g);zone=str(f['properties']['zone_id'])
        near=native_boundary or g.boundary.distance(point)<=0.05
        if inside or near:
            if zone not in links or not isinstance(links[zone],list) or not links[zone]:raise CollectionError('CATCHMENT_SCHOOL_JOIN_REQUIRED')
            matched.append(zone);boundary=boundary or near
    schools=sorted({str(code) for zone in matched for code in links[zone]})
    return {'status':'BOUNDARY' if boundary else 'MULTIPLE' if len(matched)>1 or len(schools)>1 else 'UNIQUE_INTERIOR' if matched else 'NO_MATCH',
        'zone_ids':matched,'school_codes':schools,'target_id':spec['target_id'],'lon':spec['lon'],'lat':spec['lat'],
        'source_crs':crs.to_string(),'tested_crs':'EPSG:5179','boundary_tolerance_m':0.05,'basis_date':spec['basis_date'],
        'geometry_sha256':spec['geometry_sha256'],'join_sha256':spec['join_sha256']}

def collect_address(source,params,run,key):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import integrations
    from quality import normalize
    now=D.datetime.now(D.timezone.utc).isoformat();raw=Path(run)/'raw/S07/address-response.json';rows=[];error=None;calls=0
    try:
        calls+=1
        payload=json.loads(integrations.cli(['geocode',params['address'],'--type',params.get('type','ROAD')],key))
        write(raw,payload)
        lon,lat=integrations.match_address(payload,params['expected_tokens'])
        r=payload.get('result',{}) if 'ok' in payload else payload;r=r.get('response',r)
        refined=r.get('refined',{}).get('text')
        if not isinstance(refined,str) or not refined:raise ValueError('VWORLD_REFINED_ADDRESS_REQUIRED')
        reverse_type='PARCEL' if params.get('type','ROAD')=='ROAD' else 'ROAD'
        calls+=1
        reverse=json.loads(integrations.cli(['geocode',str(lon)+','+str(lat),'--reverse','--type',reverse_type],key))
        reverse_file=raw.with_name('address-reverse.json');write(reverse_file,reverse)
        rr=reverse.get('result',{}) if 'ok' in reverse else reverse;rr=rr.get('response',rr)
        candidates=rr.get('result',[])
        if rr.get('status')!='OK' or not isinstance(candidates,list) or len(candidates)!=1:raise ValueError('VWORLD_AMBIGUOUS_CANDIDATES')
        other=candidates[0].get('text')
        if not other or candidates[0].get('type','').upper()!=reverse_type:raise ValueError('VWORLD_REVERSE_ADDRESS_REQUIRED')
        road=refined if reverse_type=='PARCEL' else other
        parcel=other if reverse_type=='PARCEL' else refined
        structure=r.get('refined',{}).get('structure',{});back=candidates[0].get('structure',{})
        if any(structure.get(k) and structure[k]!=back.get(k) for k in ('level1','level2')):raise ValueError('VWORLD_REVERSE_REGION_MISMATCH')
        forward_dong=structure.get('level3') if reverse_type=='PARCEL' else structure.get('level4L')
        reverse_dong=back.get('level4L') if reverse_type=='PARCEL' else back.get('level3')
        if forward_dong and reverse_dong and forward_dong!=reverse_dong:raise ValueError('VWORLD_REVERSE_REGION_MISMATCH')
        row={'address':params['address'],'road_address':road,'parcel_address':parcel,
            'lon':lon,'lat':lat,'expected_tokens':params['expected_tokens'],'basis_date':now[:10],'location_kind':'address_lookup_point',
            'source_url':source['endpoint']}
        result=normalize(source,row,load(Path(run)/'request.json'),str(raw.relative_to(run)),now)
        result['provenance'].update(raw_sha256=digest_file(raw),execution='upstream_cli',skill_version='0.3.5',attachments=[{'archived_file':str(reverse_file.relative_to(run)),'sha256':digest_file(reverse_file)}])
        rows=[result]
    except (ValueError,OSError,KeyError,TypeError) as exc:
        error=str(exc) if isinstance(exc,ValueError) and str(exc).startswith('VWORLD_') else 'ADDRESS_RESPONSE_REVIEW_REQUIRED'
    complete=error is None
    return {'status':'COMPLETE' if complete else error,'complete':complete,'rows':rows,'returned_count':len(rows) if complete else None,
        'total_count':len(rows) if complete else None,'error':error,'warnings':[],'cached':False,'network_attempts':calls,'observed_at':now}

