"""Versioned, channel-independent evidence rules. Lists and empty rows are not evidence."""
import datetime as D
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urlparse

RULE_VERSION='2.3.0'
FORMAT_VERSION=2
REPLACED={'S07':'vworld-address-v1','S12':'official-school-v1','S17':'official-law-v1'}

def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def official_url(url):
    host=(urlparse(str(url)).hostname or '').lower()
    return host.endswith(('.go.kr','.gov.kr','.sen.go.kr','.goe.go.kr')) or host in {'schoolzone.emac.kr','www.schoolzone.emac.kr','kosis.kr','www.kosis.kr','ecos.bok.or.kr','www.bok.or.kr','www.reb.or.kr','reb.or.kr'}

def valid_date(value):
    try: return D.date.fromisoformat(str(value)).isoformat()
    except ValueError: return None

def value(row,names):
    return next((str(row[k]).strip() for k in names if row.get(k) is not None and str(row[k]).strip()),None)

def proof_matches(proof,expected):
    if not isinstance(proof,dict) or proof.get('review_status')!='VERIFIED' or not official_url(proof.get('source_url')):
        return False
    try:
        path=Path(proof['file'])
        if not path.is_file() or digest_file(path)!=proof['sha256']:return False
        if not all(str(proof.get('fields',{}).get(k))==str(v) for k,v in expected.items()):return False
        text=path.read_text(encoding='utf-8-sig')
        if proof.get('selector'):
            rows=json.loads(text)
            for key in proof.get('rows_path',[]):rows=rows[key]
            matched=[r for r in rows if all(str(r.get(k))==str(v) for k,v in proof['selector'].items())]
            if len(matched)!=1:return False
            return all(str(matched[0].get(proof.get('field_map',{}).get(k)))==str(v) for k,v in expected.items())
        return all(proof.get('field_quotes',{}).get(k) in text and str(v) in proof['field_quotes'][k] for k,v in expected.items() if proof.get('field_quotes',{}).get(k)) and all(k in proof.get('field_quotes',{}) for k in expected)
    except (KeyError,OSError,TypeError,ValueError): return False

def statistic_issues(source,row,request):
    sid=source['id'];p=request.get('params',{}).get(sid,{})
    maps={
        'S08':[('orgId',['ORG_ID']),('tblId',['TBL_ID']),('itmId',['ITM_ID']),('objL1',['C1']),('prdSe',['PRD_SE'])],
        'S09':[('STATBL_ID',['STATBL_ID']),('ITM_ID',['ITM_ID']),('CLS_ID',['CLS_ID']),('DTACYCLE_CD',['DTACYCLE_CD'])],
        'S22':[('stat_code',['STAT_CODE']),('item_code',['ITEM_CODE1']),('cycle',['CYCLE'])]
    }
    issues=[];missing={}
    if sid=='S08':maps[sid]+=[(f'objL{i}',[f'C{i}']) for i in range(2,9) if p.get(f'objL{i}')]
    if sid=='S09' and p.get('GRP_ID'):maps[sid].append(('GRP_ID',['GRP_ID']))
    if sid=='S22':maps[sid]+=[(f'item_code{i}',[f'ITEM_CODE{i}']) for i in range(2,5) if p.get(f'item_code{i}')]
    for name,fields in maps[sid]:
        expected=p.get(name);actual=value(row,fields)
        if expected is None or str(expected).strip() in ('','ALL','*'):
            issues.append('STATISTIC_EXPLICIT_SCOPE_REQUIRED:'+name);continue
        allowed=[s for s in re.split(r'[, +]',str(expected)) if s]
        if actual is None: missing[name]=expected
        elif actual not in allowed: issues.append('STATISTIC_SCOPE_MISMATCH:'+name)
    if missing and not proof_matches(request.get('scope_evidence',{}).get(sid),missing):
        issues.append('STATISTIC_METADATA_REQUIRED:'+','.join(missing))
    start,end,cycle=({'S08':('startPrdDe','endPrdDe','prdSe'),'S09':('START_WRTTIME','END_WRTTIME','DTACYCLE_CD'),'S22':('start','end','cycle')})[sid]
    c=str(p.get(cycle,'')).upper()
    c={'MM':'M','QQ':'Q','YY':'Y','DD':'D'}.get(c,c)
    def period(v):
        text=str(v or '')
        if c in ('A','Y'): return int(text) if re.fullmatch(r'\d{4}',text) else None
        if c=='M': return int(text) if re.fullmatch(r'\d{4}(0[1-9]|1[0-2])',text) else None
        if c=='Q':
            match=re.fullmatch(r'(\d{4})(?:Q|0)?([1-4])',text)
            return int(match[1])*4+int(match[2]) if match else None
        if c=='D':
            try:return D.datetime.strptime(text,'%Y%m%d').date().toordinal()
            except ValueError:return None
        return None
    observed=period(value(row,['TIME','PRD_DE','WRTTIME_IDTFR_ID']))
    a,b=period(p.get(start)),period(p.get(end))
    if None in (observed,a,b): issues.append('STATISTIC_PERIOD_OR_CYCLE_INVALID')
    elif not a<=observed<=b: issues.append('STATISTIC_PERIOD_MISMATCH')
    raw=value(row,['DT','DTA_VAL','DATA_VALUE'])
    if raw in (None,'-','...','…','x','X','..','N/A'): issues.append('STATISTIC_MISSING_VALUE')
    else:
        try:
            if not math.isfinite(float(raw.replace(',',''))):raise ValueError()
        except ValueError: issues.append('STATISTIC_VALUE_INVALID')
    unit=value(row,['UNIT_NAME','UNIT_NM','UI_NM'])
    if not unit: issues.append('STATISTIC_UNIT_REQUIRED')
    if not p.get('expected_unit'):issues.append('STATISTIC_EXPECTED_UNIT_REQUIRED')
    elif unit!=p['expected_unit']:issues.append('STATISTIC_UNIT_MISMATCH')
    return issues

def public_issues(source,row,request):
    sid=source['id'];issues=[];p=request.get('params',{}).get(sid,{})
    required={
      'S07':['address','road_address','parcel_address','lon','lat','expected_tokens','basis_date','location_kind'],
      'S12':['record_type','school_code','school_level','operating_status','address','lon','lat','basis_date','source_url'],
      'S17':['law_name','article','law_body','effective_date','jurisdiction','source_url','basis_date','addenda_review','annex_review']
    }[sid]
    issues += ['MISSING:'+k for k in required if row.get(k) is None or row.get(k)=='' or row.get(k)==[]]
    if not valid_date(row.get('basis_date')):issues.append('BASIS_DATE_REQUIRED')
    if sid in ('S12','S17') and not official_url(row.get('source_url')):issues.append('OFFICIAL_ORIGIN_REQUIRED')
    if sid in ('S07','S12'):
        try:
            if not (124<float(row['lon'])<132 and 33<float(row['lat'])<39):raise ValueError()
        except (ValueError,KeyError,TypeError): issues.append('COORDINATE_RANGE')
    if sid=='S07':
        tokens=p.get('expected_tokens',[])
        if not tokens or row.get('expected_tokens')!=tokens:issues.append('ADDRESS_EXPECTATION_MISMATCH')
        address=' '.join(str(row.get(k,'')) for k in ('road_address','parcel_address'))
        for token in tokens:
            pattern=r'(?<![\d-])'+re.escape(token)+r'(?![\d-])' if re.fullmatch(r'\d+(?:-\d+)?',token) else re.escape(token)
            if not re.search(pattern,address):issues.append('ADDRESS_TARGET_MISMATCH');break
        if row.get('location_kind')!='address_lookup_point':issues.append('ADDRESS_POINT_KIND_REQUIRED')
    if sid=='S12':
        if not p.get('school_code') or not p.get('region'):issues.append('SCHOOL_EXPLICIT_TARGET_REQUIRED')
        if row.get('operating_status') not in ('운영','운영중','운영 중','정상','ACTIVE'):issues.append('SCHOOL_NOT_ACTIVE')
        if p.get('school_code') and row.get('school_code')!=p['school_code']:issues.append('SCHOOL_CODE_MISMATCH')
        if p.get('region') and p['region'] not in str(row.get('address','')):issues.append('SCHOOL_REGION_MISMATCH')
        if row.get('record_type')=='assignment':
            for key in ['academic_year','notice_status','notice_url','notice_sha256','exception_conditions','geometry_result']:
                if row.get(key) is None or row.get(key)=='':issues.append('MISSING:'+key)
            if row.get('academic_year')!=p.get('academic_year'):issues.append('SCHOOL_YEAR_MISMATCH')
            if row.get('notice_status')!='FINAL':issues.append('FINAL_NOTICE_REQUIRED')
            if not official_url(row.get('notice_url')):issues.append('OFFICIAL_NOTICE_REQUIRED')
            result=row.get('geometry_result',{})
            if result.get('status')!='UNIQUE_INTERIOR' or result.get('school_codes')!=[row.get('school_code')]:
                issues.append('ASSIGNMENT_BOUNDARY_OR_MULTIPLE')
            if result.get('target_id')!=request.get('target',{}).get('subject_id'):issues.append('CATCHMENT_TARGET_MISMATCH')
        elif row.get('record_type')!='location':issues.append('SCHOOL_RECORD_TYPE_REQUIRED')
    if sid=='S17':
        for key in ['law_name','article','jurisdiction']:
            if not p.get('expected_'+key) or row.get(key)!=p['expected_'+key]:issues.append('LAW_SCOPE_MISMATCH:'+key)
        effective=valid_date(row.get('effective_date'));basis=request.get('basis_date',D.date.today().isoformat())
        if not effective or effective>basis:issues.append('LAW_NOT_EFFECTIVE_AT_BASIS')
        if row.get('addenda_review') not in ('REVIEWED','NONE_IN_SOURCE') or row.get('annex_review') not in ('REVIEWED','NONE_IN_SOURCE'):
            issues.append('LAW_SUPPLEMENT_REVIEW_REQUIRED')
        if p.get('intended_use'):
            if row.get('intended_use')!=p['intended_use'] or row.get('pnu')!=request.get('target',{}).get('pnu'):
                issues.append('LAND_USE_TARGET_MISMATCH')
            if not official_url(row.get('local_notice_url')):issues.append('LOCAL_USE_SOURCE_REQUIRED')
    return list(dict.fromkeys(issues))

def provenance(source,raw_file,observed_at,basis_date,channel=None):
    return {'provider':source.get('provider',source['title']),'route_id':source.get('route_id',source['id']+'-original-v1'),
        'collection_channel':channel or source['mode'],'data_format_version':FORMAT_VERSION,'validation_rule_version':RULE_VERSION,
        'raw_file':raw_file,'observed_at':observed_at,'basis_date':basis_date,
        'processing_status':'EXTRACTED_REVIEW_REQUIRED'}

def revalidate(source,record,request,run=None):
    if not source or not record.get('usable'):return False
    p=record.get('provenance',{})
    if p.get('validation_rule_version') not in (None,RULE_VERSION):return False
    if p.get('data_format_version') not in (None,FORMAT_VERSION):return False
    # A previous API approval does not certify a replacement route.
    if source['id'] in REPLACED and p.get('route_id')!=REPLACED[source['id']]:return False
    if run:
        try:
            raw=(Path(run)/p['raw_file']).resolve()
            if not raw.is_relative_to(Path(run).resolve()) or not raw.is_file():return False
            if not p.get('raw_sha256') or digest_file(raw)!=p['raw_sha256']:return False
            for attachment in p.get('attachments',[]):
                file=(Path(run)/attachment['archived_file']).resolve()
                if not file.is_relative_to(Path(run).resolve()) or digest_file(file)!=attachment['sha256']:return False
        except (KeyError,OSError,TypeError):return False
    from quality import normalize
    if run and p.get('scope_evidence'):
        import copy
        request=copy.deepcopy(request)
        proof=copy.deepcopy(p['scope_evidence'])
        original=(Path(run)/proof['archived_file']).resolve()
        if not original.is_relative_to(Path(run).resolve()):return False
        proof['file']=str(original)
        request.setdefault('scope_evidence',{})[source['id']]=proof
    if source['mode']=='API' or source['id'] in REPLACED:
        if not isinstance(record.get('raw_fields'),dict):return False
        check=normalize(source,record['raw_fields'],request,p.get('raw_file'),p.get('observed_at'),p.get('query_period'),p.get('collection_scope'))
        return check['usable'] and check['values']==record.get('values')
    return not record.get('issues') and bool(record.get('values')) and p.get('review_status')=='VERIFIED'

