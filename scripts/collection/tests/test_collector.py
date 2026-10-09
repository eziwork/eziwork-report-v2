import copy
import datetime as D
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters import CollectionError, parse, request_url
from collector import Engine, Transport, preflight, registry, ttl, months, load, write, report_readiness, Redactor
from quality import normalize,validate_input

def xml(rows,total=None,code='000'):
    items=''.join('<item>'+''.join(f'<{k}>{v}</{k}>' for k,v in r.items())+'</item>' for r in rows)
    return f'<response><header><resultCode>{code}</resultCode></header><body><items>{items}</items><totalCount>{len(rows) if total is None else total}</totalCount></body></response>'.encode()

def row(**changes):
    return {**dict(aptNm='대상',dealAmount='10,000',excluUseAr='84.5',dealYear='2026',dealMonth='8',dealDay='3',umdNm='개포동',sggCd='11680',jibun='83',umdCd='10300',cdealType=''),**changes}

def request(sources=None):
    return dict(schema_version=1,report_type='P01',sources=sources or ['T01'],
        target=dict(subject_id='test',property_name='대상',lawd_cd='11680',legal_dong='개포동',lot_number='83'),
        period=dict(start_ym='202608',end_ym='202608'),transaction_type='SALE',params={},page_size=1)

class FakeTransport:
    def __init__(self,responses): self.responses=list(responses);self.calls=[]
    def fetch(self,url):
        self.calls.append(url)
        if not self.responses: raise AssertionError('Unexpected network request')
        result=self.responses.pop(0)
        if isinstance(result,Exception): raise result
        return result,1

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.sources,self.reports=registry()
    def engine(self,responses):
        self.fake=FakeTransport(responses)
        return Engine(self.root/'runs',self.root/'cache',self.fake,{'DATA_GO_KR_SERVICE_KEY':'test-secret+value'})
    def test_registry_coverage(self):
        self.assertEqual(len(self.sources),40);self.assertEqual(len(self.reports),14)
        self.assertEqual(sum(len(r['data_requirements']) for r in self.reports),58)
        self.assertEqual(sum(s['mode']=='API' for s in self.sources.values()),25)
        for s in self.sources.values():
            for key in ['required','validation','fallback','failure_handling','guide_url','last_audit','implementation_status','production_status']: self.assertIn(key,s)
            if s['mode']!='API': self.assertTrue((Path(__file__).resolve().parents[1]/'forms'/f'{s["id"]}.json').exists())
        for r in self.reports:
            for g in r['data_requirements']: self.assertTrue(set(g['sources'])<=self.sources.keys())
    def test_pagination_and_cache(self):
        e=self.engine([xml([row()],2),xml([row(dealDay='4')],2)])
        run,m=e.collect(request(),'first');self.assertTrue(m['sources']['T01']['complete'])
        self.assertEqual(m['sources']['T01']['returned_count'],2)
        self.assertEqual(m['sources']['T01']['usable_count'],2)
        _,cached=e.collect(request(),'second')
        self.assertEqual(len(self.fake.calls),2)
        self.assertTrue(cached['sources']['T01']['chunks'][0]['cached'])
        self.assertEqual(cached['sources']['T01']['chunks'][0]['network_attempts'],0)
        self.assertEqual(len(list((self.root/'runs/second/raw/T01').glob('*.txt'))),2)
    def test_normal_empty_is_not_missing(self):
        e=self.engine([xml([],0)])
        _,m=e.collect(request(),'empty');self.assertEqual(m['sources']['T01']['returned_count'],0)
        self.assertEqual(m['sources']['T01']['status'],'COMPLETE')
        self.assertEqual(m['readiness'][0]['status'],'HOLD')
        _,m=Engine(self.root/'missing',self.root/'cache',credentials={}).collect(request(),'missing')
        self.assertIsNone(m['sources']['T01']['returned_count'])
    def test_auth_failure_is_not_zero_and_attempt_is_recorded(self):
        e=self.engine([CollectionError('AUTH_REJECTED')]);_,m=e.collect(request(),'auth')
        self.assertIsNone(m['sources']['T01']['returned_count'])
        self.assertEqual(m['sources']['T01']['chunks'][0]['network_attempts'],1)
    def test_resume_partial(self):
        e=self.engine([xml([row()],2),CollectionError('TIMEOUT')])
        run,m=e.collect(request(),'resume')
        self.assertEqual(m['sources']['T01']['status'],'PARTIAL')
        self.assertFalse(load(run/'normalized/T01.json')[0]['usable'])
        e.transport=FakeTransport([xml([row(dealDay='4')],2)])
        _,m=e.collect(request(),'resume',resume=True)
        self.assertTrue(m['sources']['T01']['complete'])
        self.assertEqual(len(e.transport.calls),1)
        self.assertIn('pageNo=2',e.transport.calls[0])
    def test_repeated_and_empty_pages_stop(self):
        for second,expected in [(xml([row()],2),'REPEATED_PAGE'),(xml([],2),'EARLY_EMPTY_PAGE')]:
            e=self.engine([xml([row()],2),second]);_,m=e.collect(request(),expected)
            self.assertFalse(m['sources']['T01']['complete'])
            self.assertEqual(m['sources']['T01']['chunks'][0]['error'],expected)
    def test_total_change_stops(self):
        e=self.engine([xml([row()],2),xml([row(dealDay='4')],3)])
        _,m=e.collect(request(),'count');self.assertEqual(m['sources']['T01']['chunks'][0]['error'],'TOTAL_COUNT_CHANGED')
    def test_page_limit(self):
        e=self.engine([xml([row()],2)]);req=request();req['max_pages']=1
        _,m=e.collect(req,'bounded');self.assertEqual(m['sources']['T01']['chunks'][0]['error'],'PAGE_LIMIT_REACHED')
    def test_force_refresh(self):
        e=self.engine([xml([row()]),xml([row(dealDay='4')])]);e.collect(request(),'a');_,m=e.collect(request(),'b',force=True)
        self.assertFalse(m['sources']['T01']['chunks'][0]['cached']);self.assertEqual(len(self.fake.calls),2)
    def test_invalid_request_is_rejected(self):
        e=self.engine([]);req=request();req['sources']=['../nope']
        with self.assertRaises(CollectionError): e.collect(req)
        with self.assertRaises(CollectionError): e.collect(request(),'../outside')
        req=request();req['params']={'T01':{'serviceKey':'unsafe'}}
        with self.assertRaises(CollectionError): e.collect(req)
    def test_target_and_rent_and_cancellation(self):
        s=self.sources['T01'];r=row();r.pop('aptNm')
        self.assertFalse(normalize(s,r,request(),'raw',D.datetime.now().isoformat())['usable'])
        r=row();r['cdealType']='N'
        self.assertFalse(normalize(s,r,request(),'raw','now')['values']['cancelled'])
        r['cdealType']='O';self.assertFalse(normalize(s,r,request(),'raw','now')['usable'])
        r=row();r.pop('dealAmount');r['deposit']='1000'
        out=normalize(self.sources['T07'],r,request(),'raw','now')
        self.assertEqual(out['values']['trade_type'],'UNKNOWN');self.assertFalse(out['usable'])
        r['monthlyRent']='0';out=normalize(self.sources['T07'],r,{**request(),'transaction_type':'JEONSE'},'raw','now')
        self.assertEqual(out['values']['trade_type'],'JEONSE');self.assertTrue(out['usable'])
    def test_identical_values_are_not_deduplicated_within_page(self):
        e=self.engine([xml([row(),row()],2)]);_,m=e.collect(request(),'duplicate-values')
        self.assertEqual(m['sources']['T01']['returned_count'],2)
    def test_bad_response_not_success(self):
        for body in [b'<html>success</html>',xml([],0,code='30'),b'broken',b'{"response":{"body":{}}}']:
            with self.assertRaises(CollectionError): parse(self.sources['T01'],body)
    def test_secret_redaction(self):
        e=self.engine([xml([row()])]);run,m=e.collect(request(),'redacted')
        for p in run.rglob('*'):
            if p.is_file(): self.assertNotIn('test-secret',p.read_text(encoding='utf-8'))
        red=Redactor(['private+secret'])
        self.assertNotIn('private',red.text('private%2Bsecret private+secret'))
    def test_cache_ttl_and_periods(self):
        self.assertEqual(ttl(self.sources['T01'],'202608',D.date(2026,10,8)),86400)
        self.assertEqual(ttl(self.sources['T01'],'202607',D.date(2026,10,8)),604800)
        self.assertEqual(months('202512','202602'),['202512','202601','202602'])
        with self.assertRaises(CollectionError): months('202613','202601')
    def test_example_inputs_do_not_unlock_report(self):
        e=self.engine([]);req=request(['M01']);payload=dict(source_id='M01',evidence_mode='EXAMPLE',review_status='VERIFIED',source_url='local:test',basis_date='2026-10-08',identity={'subject_id':'test'},records=[dict(subject_id='test',purpose='buy',budget_krw=100)])
        file=self.root/'input.json';write(file,payload);run,m=e.import_file(req,file)
        self.assertEqual(m['sources']['M01']['usable_count'],0)
        self.assertFalse(load(run/'normalized/M01.json')[0]['usable'])
        self.assertEqual(len(self.fake.calls),0)
    def test_actual_manual_input_and_bad_record(self):
        e=self.engine([]);req=request(['M01']);payload=dict(source_id='M01',evidence_mode='ACTUAL',review_status='VERIFIED',source_url='local:test',basis_date='2026-10-08',identity={'subject_id':'test'},records=[dict(subject_id='test',purpose='buy',budget_krw=100)])
        file=self.root/'input.json';write(file,payload);run,m=e.import_file(req,file)
        self.assertEqual(m['sources']['M01']['usable_count'],1)
        payload['records'].append(dict(subject_id='test',purpose='buy',budget_krw=-1));write(file,payload)
        run,m=e.import_file(req,file,run.name)
        self.assertEqual(m['sources']['M01']['usable_count'],0)
        self.assertTrue(all(not r['usable'] for r in load(run/'normalized/M01.json')))
    def test_new_named_import_never_calls_network(self):
        e=self.engine([]);req=request(['M01']);payload=dict(source_id='M01',evidence_mode='ACTUAL',review_status='VERIFIED',source_url='local:test',basis_date='2026-10-08',identity={'subject_id':'test'},records=[dict(subject_id='test',purpose='buy',budget_krw=100)])
        file=self.root/'fresh-input.json';write(file,payload);run,m=e.import_file(req,file,'attachment-only')
        self.assertEqual(run.name,'attachment-only');self.assertTrue(m['sources']['M01']['complete']);self.assertEqual(len(self.fake.calls),0)
    def test_authentication_no_retry(self):
        calls=[]
        def opener(req,timeout):
            calls.append(req.full_url);raise urllib.error.HTTPError(req.full_url,403,'denied',{},None)
        t=Transport(sleep=lambda _:None,opener=opener)
        with self.assertRaises(CollectionError) as c:t.fetch('https://apis.data.go.kr/test')
        self.assertEqual(c.exception.code,'AUTH_REJECTED');self.assertEqual(len(calls),1)
    def test_documented_portal_failure_causes(self):
        for code,expected in [('30','KEY_NOT_REGISTERED'),('31','CREDENTIAL_EXPIRED_CONFIRMED'),('22','RATE_LIMITED'),('23','RATE_LIMITED'),('10','REQUEST_CONFIG_INVALID'),('05','TIMEOUT')]:
            with self.subTest(code=code):
                with self.assertRaises(CollectionError) as caught:parse(self.sources['T01'],xml([],0,code=code))
                self.assertEqual(caught.exception.code,expected)
        with self.assertRaises(CollectionError) as caught:parse(self.sources['T01'],xml([],0,code='20'))
        self.assertEqual(caught.exception.code,'AUTH_REJECTED')
    def test_transient_retries_bounded(self):
        calls=[];delays=[]
        def opener(req,timeout):
            calls.append(1);raise urllib.error.HTTPError(req.full_url,429,'limited',{'Retry-After':'1'},None)
        with self.assertRaises(CollectionError):Transport(sleep=delays.append,opener=opener).fetch('https://apis.data.go.kr/test')
        self.assertEqual(len(calls),3);self.assertEqual(delays,[1,1])
    def test_timeout_and_malformed_payload(self):
        calls=[]
        def opener(req,timeout): calls.append(1);raise socket.timeout()
        with self.assertRaises(CollectionError):Transport(sleep=lambda _:None,opener=opener).fetch('https://apis.data.go.kr/test')
        self.assertEqual(len(calls),3)
    def test_replay_real_recorded_samples(self):
        base=Path(__file__).resolve().parent/'fixtures'
        for id,file in [('T01','samples/T01-detail.xml'),('T02','samples/T02.xml'),('T03','samples/T03.xml'),('T05','samples/T05.xml'),('T07','samples/T07.xml'),('S09','documents/D-RONE-SAMPLE.html'),('S17','documents/D-LAW-SAMPLE.html'),('S22','documents/D-ECOS-SAMPLE.html')]:
            parsed=parse(self.sources[id],(base/file).read_bytes());self.assertGreater(len(parsed.rows),0,id)
    def test_naver_incomplete_filters_and_examples(self):
        req=request(['S21']);payload=load(Path(__file__).resolve().parents[1]/'forms/S21.json')
        rows,issues=validate_input(self.sources['S21'],payload,req)
        self.assertIn('FILTERS_UNVERIFIED',issues);self.assertTrue(all(not r['usable'] for r in rows))
    def test_provider_response_fixtures(self):
        fixtures={
            'S01':{'response':{'header':{'resultCode':'00'},'body':{'items':{'item':[{'mgmBldrgstPk':'a'}]},'totalCount':1}}},
            'S02':{'response':{'header':{'resultCode':'00'},'body':{'item':{'kaptCode':'a'}}}},
            'S04':{'response':{'status':'OK','record':{'total':'1'},'result':{'featureCollection':{'features':[{'properties':{'pnu':'1'}}]}}}},
            'S07':{'results':{'common':{'errorCode':'0','totalCount':'1'},'juso':[{'roadAddr':'a'}]}},
            'S08':[{'DT':'1','PRD_DE':'2026','UNIT_NM':'명'}],
            'S12':{'resultCode':'success','list':[{'SCHUL_CODE':'a'}]},
            'S20':[{'resHeader':[{'SS_CODE':'Y','ALL_CNT':'1'}]},{'dsList':[{'PAN_ID':'a'}]}]}
        for id,data in fixtures.items():
            with self.subTest(id=id): self.assertEqual(len(parse(self.sources[id],json.dumps(data).encode()).rows),1)
    def test_missing_body_and_error_envelopes_rejected(self):
        for id,data in [('S12',{'resultCode':'success'}),('S09',{'RESULT':{'CODE':'ERROR-100'}}),('S07',{'results':{'common':{'errorCode':'E0001'}}})]:
            with self.subTest(id=id),self.assertRaises(CollectionError):parse(self.sources[id],json.dumps(data).encode())
    def test_lh_live_row_count_and_conflicting_counts(self):
        payload=[{'dsSch':[{'PAGE':'1','PG_SZ':'1'}]},
                 {'resHeader':[{'SS_CODE':'Y'}],
                  'dsList':[{'PAN_ID':'notice-1','ALL_CNT':'586'}]}]
        parsed=parse(self.sources['S20'],json.dumps(payload).encode())
        self.assertEqual(parsed.total,586)
        payload[1]['dsList'].append({'PAN_ID':'notice-2','ALL_CNT':'585'})
        with self.assertRaises(CollectionError) as error:
            parse(self.sources['S20'],json.dumps(payload).encode())
        self.assertEqual(error.exception.code,'COUNT_MISMATCH')
    def test_vworld_missing_config_fails_before_network(self):
        result=preflight(request(['S04']),{'VWORLD_API_KEY':'secret'})[0]
        self.assertEqual(result['status'],'PARAMS_REQUIRED');self.assertIn('layer_guide_url',result['missing_fields'])
    def test_input_attachment_hash_and_identity(self):
        e=self.engine([]);req=request(['M01']);payload=dict(source_id='M01',evidence_mode='ACTUAL',review_status='VERIFIED',source_url='local:test',basis_date='2026-10-08',identity={'subject_id':'wrong'},records=[dict(subject_id='test',purpose='buy',budget_krw=100)],attachments=[{'file':'missing.pdf'}])
        file=self.root/'input.json';write(file,payload);_,m=e.import_file(req,file)
        self.assertEqual(m['sources']['M01']['usable_count'],0)
        self.assertIn('TARGET_IDENTITY_UNCONFIRMED',m['sources']['M01']['issues'])
        self.assertIn('EVIDENCE_FILE_MISSING',m['sources']['M01']['issues'])
    def test_report_guard_holds_missing_data(self):
        from prepare_report_evidence import prepare
        e=self.engine([xml([row()])]);run,_=e.collect(request(),'gate')
        with self.assertRaises(CollectionError):prepare(run,'P01')
        self.assertEqual(load(run/'P01-evidence.json')['records'],[])

    def test_corrupt_cache_and_checkpoint_refresh_safely(self):
        e=self.engine([xml([row()]),xml([row(dealDay='5')])]);run,_=e.collect(request(),'original')
        cache=next((self.root/'cache').glob('*.json'));cache.write_text('broken',encoding='utf-8')
        checkpoint=next((run/'checkpoints/T01').glob('*.json'));state=load(checkpoint)
        state['pages'][0]['sha256']='tampered';write(checkpoint,state)
        _,m=e.collect(request(),'original',resume=True)
        self.assertEqual(m['sources']['T01']['usable_count'],1)
        self.assertEqual(m['sources']['T01']['chunks'][0]['warnings'],['CORRUPT_CACHE_IGNORED','CORRUPT_CHECKPOINT_IGNORED'])
        self.assertEqual(len(self.fake.calls),2)

    def test_conflicting_input_identity_and_record(self):
        req=request(['M02']);req['target']['property_id']='property-a'
        payload=dict(source_id='M02',evidence_mode='ACTUAL',review_status='VERIFIED',source_url='local:test',basis_date='2026-10-08',
            identity={'subject_id':'test','property_id':'property-b'},records=[dict(property_id='property-b',transaction_type='SALE',asking_price_krw=100)])
        rows,issues=validate_input(self.sources['M02'],payload,req)
        self.assertIn('CONFLICTING_TARGET_IDENTITY',issues);self.assertIn('RECORD_TARGET_MISMATCH',rows[0]['issues'])
        self.assertFalse(rows[0]['usable'])

    def test_actual_naver_sample_and_filter_mismatch(self):
        base=Path(__file__).resolve().parent/'fixtures'
        req=load(base/'naver-request.json');payload=load(base/'naver-input.json')
        rows,issues=validate_input(self.sources['S21'],payload,req)
        self.assertEqual(issues,[]);self.assertTrue(rows[0]['usable'])
        payload['records'][0]['area_sqm']=59.9
        rows,issues=validate_input(self.sources['S21'],payload,req)
        self.assertFalse(rows[0]['usable']);self.assertIn('AREA_FILTER_MISMATCH',rows[0]['issues'])
        payload['records']=[]
        _,issues=validate_input(self.sources['S21'],payload,req);self.assertIn('EMPTY_BROWSER_SAMPLE_INCOMPLETE',issues)

    def test_reference_success_does_not_prove_identity(self):
        out=normalize(self.sources['S01'],{'mgmBldrgstPk':'a'},request(),'raw','now')
        self.assertFalse(out['usable']);self.assertIn('REFERENCE_TARGET_REVIEW_REQUIRED',out['issues'])
        out=normalize(self.sources['S08'],{'DT':'-1.2','PRD_DE':'202608','UNIT_NM':'%'},request(),'raw','now')
        self.assertTrue(out['usable'])
        out=normalize(self.sources['S08'],{'DT':'NaN','PRD_DE':'202608','UNIT_NM':'%'},request(),'raw','now')
        self.assertFalse(out['usable'])

    def test_law_body_is_distinct_from_search_and_date_checked(self):
        body='<법령><기본정보><법령ID>001248</법령ID><법령명_한글>주택임대차보호법</법령명_한글><시행일자>20260102</시행일자></기본정보><조문><조문단위><조문번호>1</조문번호><조문내용>OFFLINE SCHEMA FIXTURE</조문내용></조문단위></조문></법령>'.encode()
        s=self.sources['S17'];p=parse(s,body);self.assertTrue(p.terminal)
        req=request(['S17']);req['params']={'S17':{'ID':'001248','expected_law_name':'주택임대차보호법'}}
        self.assertIn('lawService.do',request_url(s,req['params']['S17'],1,100,'private'))
        self.assertNotIn('expected_law_name',request_url(s,req['params']['S17'],1,100,'private'))
        self.assertEqual(preflight(req,{'LAW_OC':'private'})[0]['status'],'READY_TO_TEST')
        self.assertTrue(normalize(s,p.rows[0],req,'raw','now')['usable'])
        req['basis_date']='2025-01-01';self.assertFalse(normalize(s,p.rows[0],req,'raw','now')['usable'])

    def test_csv_files_accumulate_and_pdf_needs_review(self):
        from prepare_input import prepare
        from pypdf import PdfWriter
        a=self.root/'a.csv';b=self.root/'b.csv'
        a.write_text('property_id,issued_at,rights_summary\na,2026-10-08,OFFLINE FIXTURE A\n',encoding='utf-8')
        b.write_text('property_id,issued_at,rights_summary\nb,2026-10-08,OFFLINE FIXTURE B\n',encoding='utf-8')
        envelope=load(prepare('S15',[a,b],self.root/'prepared',privacy_reviewed=True))
        self.assertEqual(len(envelope['records']),2);self.assertEqual(envelope['review_status'],'PENDING')
        writer=PdfWriter();writer.add_blank_page(width=100,height=100);pdf=self.root/'blank.pdf'
        with pdf.open('wb') as f:writer.write(f)
        with self.assertRaises(CollectionError):prepare('S15',[pdf],self.root/'pdf-input',privacy_reviewed=True)
        self.assertFalse((self.root/'pdf-input').exists())

    def test_group_provider_presence_requires_coverage_review(self):
        from prepare_report_evidence import prepare,review_coverage
        e=self.engine([]);req=request(['M03']);req['report_type']='P13';req['target']['property_id']='a'
        payload=dict(source_id='M03',evidence_mode='ACTUAL',review_status='VERIFIED',source_url='local:offline-fixture',
            basis_date='2026-10-08',identity={'subject_id':'test','property_id':'a'},records=[dict(property_id='a',basis_date='2026-10-08',
            rent_received_krw=100,operating_cost_krw=10,ledger='OFFLINE FIXTURE, not live evidence')])
        file=self.root/'ledger.json';write(file,payload);run,m=e.import_file(req,file)
        with self.assertRaises(CollectionError):prepare(run,'P13')
        report=next(r for r in e.reports if r['id']=='P13')
        reviews=dict(run_id=run.name,reviews=[dict(requirement_id=g['requirement_id'],review_status='VERIFIED',review_note='OFFLINE validation fixture',
            coverage={item:dict(source_id='M03',record_index=0,fields=['ledger']) for item in g['coverage_checklist']}) for g in report['data_requirements'][:2]])
        coverage=self.root/'review.json';write(coverage,reviews);review_coverage(run,coverage)
        self.assertEqual(load(prepare(run,'P13'))['status'],'READY_WITH_DECLARED_SCOPE')
        rows=load(run/'normalized/M03.json');rows[0]['values']['ledger']='changed';write(run/'normalized/M03.json',rows)
        with self.assertRaises(CollectionError):prepare(run,'P13')

    def test_unconditional_required_suffix_is_not_optional(self):
        report=next(r for r in self.reports if r['id']=='P14')
        state=report_readiness(request(),{'sources':{}},[report])[0]
        self.assertTrue(state['groups'][1]['required']);self.assertEqual(state['groups'][1]['status'],'HOLD')

    def test_official_file_fallback_never_claims_live_api(self):
        e=self.engine([]);req=request();original=self.root/'official.json';write(original,[row()])
        payload=dict(source_id='T01',evidence_mode='ACTUAL',review_status='VERIFIED',source_url='https://rt.molit.go.kr/',
            basis_date='2026-10-08',identity={'subject_id':'test'},api_file_mode=True,native_units_confirmed=True,
            attachments=[{'file':'official.json'}],records=[row(),row(aptNm='other')])
        file=self.root/'fallback.json';write(file,payload);run,m=e.import_file(req,file)
        state=m['sources']['T01'];self.assertEqual(state['usable_count'],1);self.assertEqual(state['returned_count'],2)
        self.assertEqual(state['production_status'],'OFFICIAL_FILE_REVIEWED');self.assertEqual(len(self.fake.calls),0)
        self.assertEqual(load(run/'normalized/T01.json')[0]['values']['price_krw'],100000000)
        payload['native_units_confirmed']=False;write(file,payload)
        _,m=e.import_file(req,file,run.name);self.assertEqual(m['sources']['T01']['usable_count'],0)

    def test_credential_in_attachment_is_not_archived(self):
        e=self.engine([]);req=request(['M01']);original=self.root/'accidental-secret.txt'
        original.write_text('test-secret+value',encoding='utf-8')
        payload=dict(source_id='M01',evidence_mode='ACTUAL',review_status='VERIFIED',source_url='local:offline-fixture',
            basis_date='2026-10-08',identity={'subject_id':'test'},records=[dict(subject_id='test',purpose='buy',budget_krw=100)],
            attachments=[{'file':original.name}])
        file=self.root/'input.json';write(file,payload);run,m=e.import_file(req,file)
        self.assertIn('CREDENTIAL_IN_EVIDENCE_FILE',m['sources']['M01']['issues'])
        self.assertEqual(m['sources']['M01']['usable_count'],0)
        for p in run.rglob('*'):
            if p.is_file(): self.assertNotIn(b'test-secret+value',p.read_bytes())

if __name__=='__main__':unittest.main(verbosity=2)
