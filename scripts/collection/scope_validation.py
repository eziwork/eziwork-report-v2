"""Explicit date and geographic/property scope checks. Query inputs are never row evidence."""
import datetime as D
import re
from adapters import CollectionError

POLICY_VERSION=2
PROVINCES={'11':'서울특별시','12':'전남광주통합특별시','26':'부산광역시','27':'대구광역시',
           '28':'인천광역시','30':'대전광역시','31':'울산광역시','36110':'세종특별자치시',
           '41':'경기도','43':'충청북도','44':'충청남도','47':'경상북도','48':'경상남도',
           '50':'제주특별자치도','51':'강원특별자치도','52':'전북특별자치도'}

def compact(value): return re.sub(r'\s+','',str(value or '')).casefold()

def iso_date(value):
    text=str(value or '').strip().replace('.','-').replace('/','-')
    if re.fullmatch(r'\d{8}',text):text=f'{text[:4]}-{text[4:6]}-{text[6:]}'
    try:return D.date.fromisoformat(text).isoformat()
    except ValueError:return None

def lh_parameters(params,filters=None):
    p=dict(params);filters=filters or {}
    if any(k in p for k in ['PAN_NT_ST_DT','CLSG_DT']):
        raise CollectionError('LH_RESPONSE_FIELD_USED_AS_FILTER')
    mapping={'published_from':'PAN_ST_DT','published_to':'PAN_ED_DT',
             'closing_from':'CLSG_ST_DT','closing_to':'CLSG_ED_DT'}
    if set(filters)-set(mapping):raise CollectionError('INVALID_LH_DATE_FILTER')
    for friendly,native in mapping.items():
        if friendly in filters:
            value=iso_date(filters[friendly])
            if not value:raise CollectionError('INVALID_LH_DATE_FILTER')
            value=value.replace('-','')
            if native in p and p[native]!=value:raise CollectionError('CONFLICTING_LH_DATE_FILTER')
            p[native]=value
    for a,b in [('PAN_ST_DT','PAN_ED_DT'),('CLSG_ST_DT','CLSG_ED_DT')]:
        if bool(p.get(a))!=bool(p.get(b)):raise CollectionError('LH_DATE_RANGE_PAIR_REQUIRED')
        if p.get(a):
            if any(not re.fullmatch(r'\d{8}',str(p[k])) or not iso_date(p[k]) for k in [a,b]):
                raise CollectionError('INVALID_LH_DATE_FILTER')
            if str(p[a])>str(p[b]):raise CollectionError('INVALID_LH_DATE_RANGE')
    return p

def validate_lh_scope(page,params):
    """Validate the effective provider filters and every returned record, including zero pages."""
    p=lh_parameters(params)
    if not p.get('PAN_ST_DT') or not p.get('PAN_ED_DT'):
        raise CollectionError('LH_PUBLICATION_PERIOD_REQUIRED')
    scope=page.query_scope or {}
    for key in ['PAN_ST_DT','PAN_ED_DT','CLSG_ST_DT','CLSG_ED_DT']:
        if p.get(key) and str(scope.get(key,''))!=str(p[key]):
            raise CollectionError('LH_APPLIED_PERIOD_MISMATCH',key)
    for row in page.rows:
        for field,a,b in [('PAN_NT_ST_DT','PAN_ST_DT','PAN_ED_DT'),('CLSG_DT','CLSG_ST_DT','CLSG_ED_DT')]:
            if not p.get(a):continue
            day=iso_date(row.get(field))
            if not day:raise CollectionError('LH_RECORD_DATE_REQUIRED',field)
            if not iso_date(p[a])<=day<=iso_date(p[b]):
                raise CollectionError('LH_RECORD_DATE_OUTSIDE_SCOPE',field)
    return dict(status='VERIFIED',policy_version=POLICY_VERSION,requested={k:p[k] for k in
        ['PAN_ST_DT','PAN_ED_DT','CLSG_ST_DT','CLSG_ED_DT'] if p.get(k)},applied=scope)

def lot(value):
    text=re.sub(r'\s+','',str(value or ''));hill=text.startswith('산');text=text.removeprefix('산')
    m=re.fullmatch(r'(\d{1,4})(?:-(\d{1,4}))?',text)
    if not m:return None
    return ('2' if hill else '1')+str(int(m[1])).zfill(4)+str(int(m[2] or 0)).zfill(4)

def parcel_id(row,source_id):
    if re.fullmatch(r'\d{19}',str(row.get('pnu',''))):return str(row['pnu'])
    if source_id in {'S01','S19'}:
        district=str(row.get('sigunguCd',''));dong=str(row.get('bjdongCd',''))
        bun=str(row.get('bun',''));ji=str(row.get('ji',''));land=str(row.get('platGbCd',''))
        if not re.fullmatch(r'\d{5}',district) or not re.fullmatch(r'\d{5}',dong):return None
        if land not in {'0','1'} or not re.fullmatch(r'\d{1,4}',bun) or not re.fullmatch(r'\d{1,4}',ji):return None
        return district+dong+('2' if land=='1' else '1')+bun.zfill(4)+ji.zfill(4)
    district=str(row.get('sggCd',''));dong=str(row.get('umdCd',''));number=lot(row.get('jibun'))
    if re.fullmatch(r'\d{5}',district) and re.fullmatch(r'\d{5}',dong) and number:return district+dong+number
    return None

def identity(source,row,request):
    t=request.get('target',{});id=source['id'];fields=row.get('properties',row)
    kind=request.get('source_scopes',{}).get(id,'PROPERTY')
    reasons=[];proofs={}
    def compare(key,actual,expected):
        if actual is None or actual=='':reasons.append('IDENTITY_FIELD_MISSING:'+key)
        elif compact(actual)!=compact(expected):reasons.append('IDENTITY_FIELD_MISMATCH:'+key)
        else:proofs[key]=actual
    if id=='S20' and kind in {'REGION','NATIONAL_CONTEXT'}:
        if kind=='REGION':
            code=str(t.get('province_code') or str(t.get('lawd_cd',''))[:2])
            expected=PROVINCES.get(code)
            if not expected:reasons.append('TARGET_PROVINCE_REQUIRED')
            else:compare('province',row.get('CNP_CD_NM'),expected)
        return dict(kind=kind,status='UNCONFIRMED' if reasons else 'MATCH',proofs=proofs,reasons=reasons)
    if id=='S10' and kind=='DISTRICT_CONTEXT':
        if not t.get('lawd_cd'):reasons.append('TARGET_DISTRICT_REQUIRED')
        else:compare('district',row.get('signguCd'),t['lawd_cd'])
        return dict(kind=kind,status='UNCONFIRMED' if reasons else 'MATCH',proofs=proofs,reasons=reasons)
    if kind!='PROPERTY':
        return dict(kind=kind,status='UNCONFIRMED',proofs={},reasons=['UNSUPPORTED_SOURCE_SCOPE'])
    district=t.get('lawd_cd')
    if source['adapter']=='rtms':
        if not district:reasons.append('TARGET_DISTRICT_REQUIRED')
        else:compare('district',row.get('sggCd'),district)
        strong=False
        if t.get('pnu'):
            strong=True;compare('pnu',parcel_id(row,id),t['pnu'])
        if t.get('legal_dong') and t.get('lot_number'):
            strong=True;compare('legal_dong',row.get('umdNm'),t['legal_dong'])
            compare('lot',lot(row.get('jibun')),lot(t['lot_number']))
        if t.get('complex_id'):
            strong=True;compare('complex_id',row.get('aptSeq'),t['complex_id'])
        if not strong:reasons.append('STRONG_TARGET_IDENTITY_REQUIRED')
        if t.get('property_name'):
            actual=next((row.get(k) for k in ['aptNm','offiNm','mhouseNm','buildingName'] if row.get(k)),None)
            compare('property_name',actual,t['property_name'])
        if t.get('property_type') and t['property_type']!=source.get('property_type'):
            reasons.append('PROPERTY_TYPE_MISMATCH')
    elif id in {'S01','S19','S04','S05','S06'}:
        if t.get('pnu'):compare('pnu',parcel_id(fields,id),t['pnu'])
        else:reasons.append('TARGET_PNU_REQUIRED')
        if id in {'S01','S19'} and t.get('legal_dong'):
            present=bool(re.search(r'(?:^|\s)'+re.escape(t['legal_dong'])+r'(?=\s|$)',str(row.get('platPlc',''))))
            compare('legal_dong',t['legal_dong'] if present else None,t['legal_dong'])
    elif id=='S02':
        if t.get('kapt_code'):compare('kapt_code',row.get('kaptCode'),t['kapt_code'])
        else:reasons.append('TARGET_KAPT_CODE_REQUIRED')
        bjd=str(row.get('bjdCode',''))
        if district:compare('district',bjd[:5] if len(bjd)==10 else None,district)
        else:reasons.append('TARGET_DISTRICT_REQUIRED')
        if t.get('pnu') and t.get('legal_dong'):
            m=re.search(r'(?:^|\s)'+re.escape(t['legal_dong'])+r'\s+(산\s*)?(\d+(?:-\d+)?)(?=\s|$)',str(row.get('kaptAddr','')))
            suffix=lot(('산' if m[1] else '')+m[2]) if m else None
            actual=bjd+suffix if suffix and len(bjd)==10 else None
            compare('pnu',actual,t['pnu'])
        else:reasons.append('TARGET_PNU_AND_DONG_REQUIRED')
    else:
        # Bindings cannot turn unrelated rows into target evidence. Only target-owned IDs qualify.
        candidates={'pnu':'pnu','bdMgtSn':'building_id','mgmBldrgstPk':'building_register_id',
                    'kaptCode':'kapt_code','SCHUL_CODE':'school_code'}
        bound=False
        for field,target_key in candidates.items():
            if t.get(target_key) and fields.get(field):
                bound=True;compare(target_key,fields[field],t[target_key])
        if not bound:reasons.append('REFERENCE_TARGET_REVIEW_REQUIRED')
    # Cross-field bindings are checked against the target, never accepted as a substitute.
    for key,expected in request.get('reference_bindings',{}).get(id,{}).items():
        compare('binding:'+key,fields.get(key),expected)
    status='MISMATCH' if any('MISMATCH' in x for x in reasons) else 'UNCONFIRMED' if reasons else 'MATCH'
    return dict(kind=kind,status=status,proofs=proofs,reasons=reasons)
