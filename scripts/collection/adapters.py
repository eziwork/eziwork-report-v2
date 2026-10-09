"""Read-only official service request builders and fail-closed response parsers."""
import json
import re
import urllib.parse as U
import xml.etree.ElementTree as ET
from dataclasses import dataclass

class CollectionError(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail

@dataclass
class Page:
    rows: list
    total: int | None
    code: str
    terminal: bool = False
    query_scope: dict | None = None

def integer(value):
    if value is None or value == '': return None
    try:
        n=int(value)
        if n < 0: raise ValueError()
        return n
    except (ValueError, TypeError): raise CollectionError('INVALID_COUNT')

def as_rows(value):
    if value in (None, ''): return []
    if isinstance(value, dict): return [value]
    if isinstance(value, list) and all(isinstance(x, dict) for x in value): return value
    raise CollectionError('RESPONSE_SCHEMA_CHANGED')

def check_code(code, accepted, public_portal=False, message=None):
    code=str(code)
    if code in accepted: return code
    if public_portal:
        messages={'SERVICE_ACCESS_DENIED_ERROR':'AUTH_APPROVAL_REQUIRED','SERVICE_KEY_IS_NULL':'KEY_MISSING','DEADLINE_HAS_EXPIRED_ERROR':'CREDENTIAL_EXPIRED_CONFIRMED'}
        codes={'30':'KEY_NOT_REGISTERED','31':'CREDENTIAL_EXPIRED_CONFIRMED','22':'RATE_LIMITED','23':'RATE_LIMITED','10':'REQUEST_CONFIG_INVALID','12':'ENDPOINT_UNAVAILABLE','05':'TIMEOUT','01':'SERVER_UNAVAILABLE'}
        if message in messages:raise CollectionError(messages[message],code)
        if code in codes:raise CollectionError(codes[code],code)
    if code in {'30','31','32','20','21','22','INVALID_KEY','INCORRECT_KEY','UNAVAILABLE_KEY',
                'ERROR-100','ERROR-101','ERROR-200','ERROR-300'}:
        raise CollectionError('AUTH_REJECTED',code)
    raise CollectionError('API_REJECTED', code[:60])

def request_url(source, params, page, size, secret):
    a=source['adapter']; q={**source.get('defaults',{}), **params}
    # Internal routing and documentation fields never go to the provider.
    for k in ['lawd_cd','start_ym','end_ym','layer_guide_url','expected_law_name']: q.pop(k,None)
    endpoint=source['endpoint']
    if a=='ecos':
        path=[secret,'json','kr',str((page-1)*size+1),str(page*size),q['stat_code'],
              q['cycle'],q['start'],q['end'],q['item_code']]
        return endpoint+'/'+ '/'.join(U.quote(str(x),safe='') for x in path)
    if a=='rtms': q.update(LAWD_CD=params['lawd_cd'],DEAL_YMD=params['month'],pageNo=page,numOfRows=size); q.pop('month',None)
    elif a=='juso': q.update(currentPage=page,countPerPage=min(size,100))
    elif a=='rone': q.update(pIndex=page,pSize=size)
    elif a=='vworld': q.update(page=page,size=size)
    elif a=='law':
        if q.get('ID') or q.get('MST'):
            endpoint=source['body_endpoint'];q.pop('query',None)
        else: q.update(page=page,display=min(size,100))
    elif a=='lh': q.update(PAGE=page,PG_SZ=size)
    elif a=='data_go' and source['id']!='S02': q.update(pageNo=page,numOfRows=size)
    if source.get('auth_param'): q[source['auth_param']]=U.unquote(secret) if a in ['rtms','data_go','lh'] else secret
    return endpoint+'?'+U.urlencode(q)

def parse(source, payload):
    try:
        txt=payload.decode('utf-8-sig')
        if '<!DOCTYPE' in txt.upper() or '<!ENTITY' in txt.upper(): raise CollectionError('UNSAFE_XML')
        if txt.lstrip().startswith(('{','[')):
            return parse_json(source,json.loads(txt))
        root=ET.fromstring(txt)
        for node in root.iter(): node.tag=node.tag.rsplit('}',1)[-1]
        if source['adapter']=='law':
            info=root.find('기본정보')
            if info is not None:
                name=info.findtext('법령명_한글');law_id=info.findtext('법령ID');effective=info.findtext('시행일자')
                articles=[' '.join(n.itertext()).strip() for n in root.findall('.//조문단위')]
                if not name or not law_id or not effective or not articles or not all(articles):
                    raise CollectionError('RESPONSE_SCHEMA_CHANGED')
                return Page([dict(law_body=True,law_id=law_id,law_name=name,effective_date=effective,articles=articles)],1,'BODY_PARSED',True)
            code=check_code(root.findtext('resultCode'),{'00'})
            return Page([{c.tag:c.text or '' for c in n} for n in root.findall('law')],integer(root.findtext('totalCnt')),code)
        code=root.findtext('.//resultCode') or root.findtext('.//returnReasonCode')
        code=check_code(code,{'0','00','000','0000'},source.get('credential')=='DATA_GO_KR_SERVICE_KEY',root.findtext('.//resultMsg') or root.findtext('.//returnAuthMsg'))
        body=root.find('.//body')
        if body is None: raise CollectionError('RESPONSE_SCHEMA_CHANGED')
        rows=[{c.tag:c.text or '' for c in n} for n in body.findall('.//item')]
        total=integer(body.findtext('.//totalCount'))
        if source['id']=='S02': return Page(rows,len(rows),code,True)
        return Page(rows,total,code)
    except CollectionError: raise
    except (ValueError, KeyError, TypeError, AttributeError, ET.ParseError, UnicodeError):
        raise CollectionError('RESPONSE_SCHEMA_CHANGED') from None

def parse_json(source, data):
    a=source['adapter']
    if a in ['rtms','data_go']:
        r=data.get('response',data)
        code=check_code(r.get('header',{}).get('resultCode'),{'0','00','000','0000'},source.get('credential')=='DATA_GO_KR_SERVICE_KEY',r.get('header',{}).get('resultMsg'))
        if 'body' not in r: raise CollectionError('RESPONSE_SCHEMA_CHANGED')
        b=r['body']; rows=as_rows(b.get('items',{}).get('item')) if isinstance(b.get('items'),dict) else as_rows(b.get('item'))
        return Page(rows,len(rows) if source['id']=='S02' else integer(b.get('totalCount')),code,source['id']=='S02')
    if a=='juso':
        r=data['results']; c=r['common']; code=check_code(c.get('errorCode'),{'0'})
        return Page(as_rows(r.get('juso')),integer(c['totalCount']),code)
    if a=='vworld':
        r=data['response']; code=check_code(r.get('status'),{'OK','NOT_FOUND'})
        if code=='NOT_FOUND': return Page([],0,code,True)
        rows=as_rows(r['result']['featureCollection']['features'])
        return Page(rows,integer(r['record']['total']),code)
    if a=='rone':
        r=data.get('SttsApiTblData')
        if not isinstance(r,list):
            check_code(data.get('RESULT',{}).get('CODE'),{'INFO-000'})
            raise CollectionError('RESPONSE_SCHEMA_CHANGED')
        head=next(x['head'] for x in r if 'head' in x)
        code=check_code(next(x['RESULT']['CODE'] for x in head if 'RESULT' in x),{'INFO-000'})
        total=next(x['list_total_count'] for x in head if 'list_total_count' in x)
        rows=next((x['row'] for x in r if 'row' in x),[])
        return Page(as_rows(rows),integer(total),code)
    if a=='ecos':
        if 'StatisticSearch' not in data:
            check_code(data.get('RESULT',{}).get('CODE'),{'INFO-200'})
            return Page([],0,'INFO-200',True)
        r=data['StatisticSearch']
        return Page(as_rows(r['row']),integer(r['list_total_count']),'INFO-000')
    if a=='kosis':
        if not isinstance(data,list): raise CollectionError('API_REJECTED',str(data.get('err','UNKNOWN'))[:60])
        rows=as_rows(data)
        if any(not {'DT','PRD_DE','UNIT_NM'} <= x.keys() for x in rows): raise CollectionError('RESPONSE_SCHEMA_CHANGED')
        if len(rows)>=10000: raise CollectionError('RESPONSE_LIMIT_REACHED')
        return Page(rows,len(rows),'SUCCESS',True)
    if a=='school':
        code=check_code(data.get('resultCode'),{'success'})
        if 'list' not in data: raise CollectionError('RESPONSE_SCHEMA_CHANGED')
        rows=as_rows(data['list']); return Page(rows,len(rows),code,True)
    if a=='lh':
        # LH publishes a header/data-list array, not the MOLIT XML envelope.
        if not isinstance(data,list): raise CollectionError('RESPONSE_SCHEMA_CHANGED')
        head=next((x['resHeader'] for x in data if 'resHeader' in x),None)
        if isinstance(head,list): head=head[0]
        if not isinstance(head,dict): raise CollectionError('RESPONSE_SCHEMA_CHANGED')
        code=check_code(head.get('SS_CODE'),{'Y'})
        lists=[x['dsList'] for x in data if 'dsList' in x]
        if len(lists)!=1:raise CollectionError('RESPONSE_SCHEMA_CHANGED')
        rows=as_rows(lists[0])
        # Live LH responses put ALL_CNT on each notice, rather than resHeader.
        counts={integer(x['ALL_CNT']) for x in rows if x.get('ALL_CNT') not in (None,'')}
        if head.get('ALL_CNT') not in (None,''): counts.add(integer(head['ALL_CNT']))
        if len(counts)>1: raise CollectionError('COUNT_MISMATCH')
        total=next(iter(counts),0 if not rows else None)
        scopes=[x['dsSch'] for x in data if 'dsSch' in x]
        scope=scopes[0][0] if len(scopes)==1 and isinstance(scopes[0],list) and len(scopes[0])==1 else None
        return Page(rows,total,code,query_scope=scope)
    raise CollectionError('RESPONSE_SCHEMA_CHANGED')
