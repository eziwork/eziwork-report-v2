"""Normalize values without inventing identity, rent, cancellation or completeness."""
import datetime as D
import math
import re
from decimal import Decimal, InvalidOperation
from scope_validation import POLICY_VERSION,identity,lh_parameters,validate_lh_scope
from adapters import CollectionError,Page
import evidence_rules as rules

def num(value, multiplier=1):
    if value is None or str(value).strip()=='': return None
    try:
        n=Decimal(str(value).replace(',','').strip())*multiplier
        if not n.is_finite() or n<0: raise InvalidOperation()
        return int(n) if n==int(n) else float(n)
    except (InvalidOperation,ValueError,OverflowError): return None

def first(row,*keys):
    return next((row[k] for k in keys if row.get(k) is not None and str(row[k]).strip()),None)

def date(value):
    if not value: return None
    text=str(value).replace('.','-').replace('/','-')
    if re.fullmatch(r'\d{8}',text): text=f'{text[:4]}-{text[4:6]}-{text[6:]}'
    try: return D.date.fromisoformat(text).isoformat()
    except ValueError: return None

def normalize(source,row,request,raw_file,observed_at,period=None,collection_scope=None):
    issues=[]; warnings=[]; values=dict(row); target=request.get('target',{})
    scope=None;basis_type='SOURCE_DATE'
    if source['adapter']=='rtms':
        name=first(row,'aptNm','offiNm','mhouseNm','buildingName')
        price=num(row.get('dealAmount'),10000); deposit=num(row.get('deposit'),10000)
        monthly=num(row.get('monthlyRent'),10000)
        area_raw=first(row,'excluUseAr','buildingAr','plottageAr','landAr')
        area=num(area_raw)
        try: contract=D.date(int(row['dealYear']),int(row['dealMonth']),int(row['dealDay'])).isoformat()
        except (KeyError,ValueError,TypeError): contract=None; issues.append('INVALID_CONTRACT_DATE')
        rent=source['trade_type']!='SALE'
        trade=('UNKNOWN' if monthly is None else 'MONTHLY_RENT' if monthly>0 else 'JEONSE') if rent else 'SALE'
        if rent and monthly is None: issues.append('MISSING_OR_INVALID_MONTHLY_RENT')
        if (deposit if rent else price) is None: issues.append('MISSING_OR_INVALID_AMOUNT')
        if area is None or area<=0: issues.append('MISSING_OR_INVALID_AREA')
        marker=str(row.get('cdealType','')).strip().upper()
        cancel_date=str(row.get('cdealDay','')).strip()
        cancelled=True if marker in {'O','Y','해제','취소'} or cancel_date else False if marker in {'','N','X'} else None
        if cancelled is None: issues.append('UNKNOWN_CANCELLATION_MARKER')
        scope=identity(source,row,request);match=scope['status']=='MATCH'
        issues.extend(scope['reasons'])
        if source['property_type'] in {'APT','ROWHOUSE','OFFICETEL'} and not name:
            issues.append('PROPERTY_NAME_REQUIRED')
        if not match: issues.append('TARGET_IDENTITY_UNCONFIRMED')
        requested=request.get('period',{})
        ym=contract[:7].replace('-','') if contract else None
        if ym and ((requested.get('start_ym') and ym<requested['start_ym']) or
                   (requested.get('end_ym') and ym>requested['end_ym']) or (period and ym!=period)):
            issues.append('TRANSACTION_DATE_OUTSIDE_PERIOD')
        if request.get('transaction_type') and trade!=request['transaction_type']: issues.append('TRANSACTION_TYPE_MISMATCH')
        bounds=request.get('area',{})
        if area is not None and ((bounds.get('min_sqm') is not None and area<bounds['min_sqm']) or
                                 (bounds.get('max_sqm') is not None and area>bounds['max_sqm'])): issues.append('AREA_OUTSIDE_SCOPE')
        values=dict(property_name=name,trade_type=trade,price_krw=price,deposit_krw=deposit,
                    monthly_rent_krw=monthly,area_sqm=area,
                    area_type='EXCLUSIVE' if row.get('excluUseAr') else 'LAND' if source['property_type']=='LAND' else 'BUILDING',
                    contract_date=contract,cancelled=cancelled,cancellation_marker=marker,
                    cancellation_date=cancel_date or None,floor_text=row.get('floor'),
                    legal_dong=row.get('umdNm'),lot_number=row.get('jibun'),
                    complex_id=row.get('aptSeq'),identity_match=match)
        basis=contract
        units={'price_krw':'KRW','deposit_krw':'KRW','monthly_rent_krw':'KRW/month','area_sqm':'m2'}
        if cancelled: issues.append('CANCELLED_TRANSACTION')
    else:
        basis=first(row,'TIME','PRD_DE','WRTTIME_IDTFR_ID','basis_date','issued_at')
        units={'source_unit':first(row,'UNIT_NAME','UNIT_NM','UI_NM')}
        # Reference/area aggregates are not proofs of a specific unit's identity.
        if source['id'] in rules.REPLACED:
            issues.extend(rules.public_issues(source,row,request))
        elif source['id'] in {'S08','S09','S22'}:
            issues.extend(rules.statistic_issues(source,row,request))
        else:
            scope=identity(source,row,request);issues.extend(scope['reasons'])
            if scope['status']!='MATCH':
                issues.append('REFERENCE_TARGET_REVIEW_REQUIRED')
            if source['id']=='S20':
                basis=date(row.get('PAN_NT_ST_DT'))
                values['published_on']=basis;values['closing_on']=date(row.get('CLSG_DT'))
                try:
                    if not collection_scope or collection_scope.get('status')!='VERIFIED':
                        raise CollectionError('LH_PERIOD_SCOPE_UNVERIFIED')
                    p=lh_parameters(request.get('params',{}).get('S20',{}),request.get('date_filters',{}).get('S20'))
                    validate_lh_scope(Page([row],1,'Y',query_scope=collection_scope.get('applied')),p)
                except CollectionError as exc:issues.append(exc.code)
            elif source['id'] in {'S01','S02','S10','S13','S19'} and not basis:
                # The response is an observed snapshot; do not invent a provider update date.
                basis_type='OBSERVED_SNAPSHOT'
                try:
                    timestamp=D.datetime.fromisoformat(observed_at)
                    if timestamp.tzinfo is None:raise ValueError()
                except (ValueError,TypeError):issues.append('INVALID_OBSERVED_AT')
                warnings.append('PROVIDER_BASIS_DATE_NOT_SUPPLIED')
            if not basis and basis_type!='OBSERVED_SNAPSHOT':issues.append('REFERENCE_BASIS_REVIEW_REQUIRED')
        values['query_scope']=request.get('params',{}).get(source['id'],{})
    if scope is not None:values['identity_scope']=scope
    return dict(source_id=source['id'],data_kind=source['data_kind'],values=values,raw_fields=row,
                provenance=dict(**rules.provenance(source,raw_file,observed_at,basis),source_url=source.get('body_endpoint') if row.get('law_body') else row.get('source_url',source['endpoint']),
                                basis_type=basis_type,query_period=period,units=units,
                                collection_scope=collection_scope,scope_policy_version=POLICY_VERSION,review_status='AUTOMATED_CHECK'),
                warnings=warnings,issues=list(dict.fromkeys(issues)),usable=not issues)

def current_api_usable(source,record,request):
    """Recheck old or edited normalized evidence before coverage review or report export."""
    return rules.revalidate(source,record,request)

def validate_input(source, payload, request):
    problems=[]; rows=[]
    if payload.get('source_id')!=source['id']: problems.append('SOURCE_ID_MISMATCH')
    if payload.get('evidence_mode') not in {'ACTUAL','EXAMPLE'}: problems.append('EVIDENCE_MODE_REQUIRED')
    if payload.get('review_status')!='VERIFIED': problems.append('REVIEW_REQUIRED')
    if not payload.get('source_url'): problems.append('SOURCE_LOCATION_REQUIRED')
    if not (date(payload.get('basis_date')) or date(payload.get('issued_at'))): problems.append('BASIS_OR_ISSUE_DATE_REQUIRED')
    records=payload.get('records')
    if not isinstance(records,list): return [],problems+['RECORDS_REQUIRED']
    target=request.get('target',{})
    identity=payload.get('identity',{})
    matched=any(target.get(k) and str(identity.get(k))==str(target[k]) for k in ['subject_id','property_id','pnu'])
    if not matched: problems.append('TARGET_IDENTITY_UNCONFIRMED')
    if any(target.get(k) and identity.get(k) and str(identity[k])!=str(target[k]) for k in ['subject_id','property_id','pnu']):
        problems.append('CONFLICTING_TARGET_IDENTITY')
    observation=payload.get('observation',{})
    if source['id']=='S21':
        if observation.get('filters_verified') is not True or observation.get('filters')!=request.get('naver_filters',{}): problems.append('FILTERS_UNVERIFIED')
        if observation.get('target_id')!=target.get('subject_id'): problems.append('BROWSER_TARGET_MISMATCH')
        if not observation.get('captured_at') or not observation.get('evidence_files'): problems.append('BROWSER_EVIDENCE_REQUIRED')
        if observation.get('stopped_reason'): problems.append(str(observation['stopped_reason']))
        if observation.get('scope') not in {'SAMPLE','ALL_VISIBLE'}: problems.append('SAMPLING_SCOPE_REQUIRED')
        if len(records)>20: problems.append('BROWSER_SAMPLE_LIMIT')
        if not isinstance(observation.get('raw_ad_count'),int) or observation['raw_ad_count']<len(records): problems.append('INVALID_AD_COUNT')
        if not isinstance(observation.get('displayed_total'),int) or observation['displayed_total']<len(records): problems.append('INVALID_DISPLAYED_COUNT')
        if not isinstance(observation.get('group_card_count'),int) or observation['group_card_count']<0: problems.append('INVALID_GROUP_COUNT')
        if not records and observation.get('displayed_total')!=0: problems.append('EMPTY_BROWSER_SAMPLE_INCOMPLETE')
        if observation.get('scope')=='ALL_VISIBLE' and observation.get('displayed_total')!=len(records): problems.append('BROWSER_COVERAGE_INCOMPLETE')
    seen=set()
    for r in records:
        if not isinstance(r,dict): problems.append('INVALID_RECORD'); continue
        issues=[f'MISSING:{k}' for k in source['input_fields'] if r.get(k) is None or r.get(k)=='']
        if any(target.get(k) and r.get(k) and str(r[k])!=str(target[k]) for k in ['subject_id','property_id','pnu']):
            issues.append('RECORD_TARGET_MISMATCH')
        for k,v in r.items():
            if k.endswith(('_krw','_sqm')) and v is not None and num(v) is None: issues.append(f'INVALID_NUMBER:{k}')
            if k in {'basis_date','issued_at','confirmed_at','inspection_date'} and v and not date(v): issues.append(f'INVALID_DATE:{k}')
        if source['id']=='S21':
            if r.get('card_detail_match') is not True: issues.append('CARD_DETAIL_COMPARISON_REQUIRED')
            if r.get('transaction_type')!=request.get('transaction_type'): issues.append('TRANSACTION_TYPE_MISMATCH')
            if r.get('area_type') not in {'EXCLUSIVE','SUPPLY','LAND','BUILDING'}: issues.append('AREA_TYPE_REQUIRED')
            if r.get('transaction_type')=='MONTHLY_RENT':
                for field in ['deposit_krw','monthly_rent_krw']:
                    if num(r.get(field)) is None: issues.append('MISSING_OR_INVALID:'+field)
            try:
                observed=D.datetime.fromisoformat(str(r.get('observed_at')))
                if observed.tzinfo is None: raise ValueError()
                if date(r.get('confirmed_at')) and date(r['confirmed_at'])>observed.date().isoformat(): issues.append('CONFIRMATION_AFTER_OBSERVATION')
            except ValueError: issues.append('INVALID_OBSERVED_AT')
            filters=request.get('naver_filters',{})
            expected=filters.get('exclusive_area_sqm')
            if expected is not None and (r.get('area_type')!='EXCLUSIVE' or num(r.get('area_sqm')) is None or abs(num(r['area_sqm'])-expected)>0.01):
                issues.append('AREA_FILTER_MISMATCH')
            article=str(r.get('article_no',''))
            if not re.fullmatch(r'\d+',article) or not re.fullmatch(r'https://fin\.land\.naver\.com/articles/'+re.escape(article)+r'/?',str(r.get('url',''))): issues.append('INVALID_ARTICLE_LINK')
            if article in seen: continue
            seen.add(article)
        if source['id'] in rules.REPLACED:
            issues.extend(rules.public_issues(source,r,request))
        rows.append(dict(raw_fields=r,source_id=source['id'],data_kind=source['data_kind'],values=r,
            provenance=dict(**rules.provenance(source,None,None,payload.get('basis_date'),'FILE'),source_url=payload.get('source_url'),
                issued_at=payload.get('issued_at'),review_status=payload.get('review_status'),
                evidence_mode=payload.get('evidence_mode'),units={k:'KRW' if k.endswith('_krw') else 'm2' for k in r if k.endswith(('_krw','_sqm'))}),
            issues=issues,usable=not issues and not problems and payload.get('evidence_mode')=='ACTUAL'))
    if payload.get('evidence_mode')=='EXAMPLE': problems.append('EXAMPLE_NOT_PRODUCTION_EVIDENCE')
    return rows,sorted(set(problems))
