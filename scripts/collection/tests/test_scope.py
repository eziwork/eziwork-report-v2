"""Scope regressions: accepted HTTP envelopes must not bypass dates or target identity."""
import copy
import datetime as D
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters import CollectionError,Page,parse
from collector import Engine,registry,load,write,parameters
from quality import normalize,current_api_usable
from scope_validation import lh_parameters,validate_lh_scope,identity
from test_collector import request,row,FakeTransport,xml

STAMP='2026-10-08T09:00:00+00:00'

class ScopeTests(unittest.TestCase):
    def setUp(self):self.sources,self.reports=registry()
    def test_lh_request_and_response_date_names_are_distinct(self):
        p=lh_parameters({},dict(published_from='2026-08-01',published_to='2026-08-07',
                                closing_from='2026-10-01',closing_to='2026-10-07'))
        self.assertEqual(p,dict(PAN_ST_DT='20260801',PAN_ED_DT='20260807',CLSG_ST_DT='20261001',CLSG_ED_DT='20261007'))
        for old in ['PAN_NT_ST_DT','CLSG_DT']:
            with self.assertRaises(CollectionError):lh_parameters({old:'2026.08.01'})
        for p in [dict(PAN_ST_DT='20260801'),dict(PAN_ST_DT='20260230',PAN_ED_DT='20260301'),
                  dict(PAN_ST_DT='20260807',PAN_ED_DT='20260801')]:
            with self.assertRaises(CollectionError):lh_parameters(p)
    def test_lh_period_echo_required_even_for_zero(self):
        p=dict(PAN_ST_DT='20260801',PAN_ED_DT='20260807')
        self.assertEqual(validate_lh_scope(Page([],0,'Y',query_scope=p),p)['status'],'VERIFIED')
        for scope in [None,{},dict(PAN_ST_DT='20260808',PAN_ED_DT='20261008')]:
            with self.assertRaises(CollectionError):validate_lh_scope(Page([],0,'Y',query_scope=scope),p)
        payload=[{'dsSch':[p]},{'resHeader':[{'SS_CODE':'Y'}],'dsList':[]}]
        self.assertEqual(parse(self.sources['S20'],json.dumps(payload).encode()).total,0)
        payload[1].pop('dsList')
        with self.assertRaises(CollectionError):parse(self.sources['S20'],json.dumps(payload).encode())
    def test_lh_publication_and_closing_boundaries(self):
        p=dict(PAN_ST_DT='20260801',PAN_ED_DT='20260807',CLSG_ST_DT='20261001',CLSG_ED_DT='20261007')
        for published,closing in [('2026.08.01','2026.10.01'),('2026.08.07','2026.10.07')]:
            validate_lh_scope(Page([dict(PAN_NT_ST_DT=published,CLSG_DT=closing)],1,'Y',query_scope=p),p)
        for changed in [dict(PAN_NT_ST_DT='2026.07.31'),dict(PAN_NT_ST_DT='2026.08.08'),
                        dict(CLSG_DT='2026.10.08'),dict(CLSG_DT='')]:
            row=dict(PAN_NT_ST_DT='2026.08.03',CLSG_DT='2026.10.03');row.update(changed)
            with self.assertRaises(CollectionError):validate_lh_scope(Page([row],1,'Y',query_scope=p),p)
    def test_lh_wrong_scope_retained_but_cannot_unlock_analysis(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            req=request(['S20']);req['params']={'S20':dict(PAN_ST_DT='20260801',PAN_ED_DT='20260807')}
            req['source_scopes']={'S20':'NATIONAL_CONTEXT'}
            body=json.dumps([{'dsSch':[dict(PAN_ST_DT='20260808',PAN_ED_DT='20261008')]},
                             {'resHeader':[{'SS_CODE':'Y'}],'dsList':[]}]).encode()
            e=Engine(Path(directory)/'runs',Path(directory)/'cache',FakeTransport([body]),{'DATA_GO_KR_SERVICE_KEY':'offline-secret'})
            run,m=e.collect(req,'ignored')
            self.assertFalse(m['sources']['S20']['complete']);self.assertEqual(m['sources']['S20']['usable_count'],0)
            self.assertTrue(list((run/'raw_rejected/S20').glob('*.txt')))
    def test_same_name_different_district_dong_or_lot_is_rejected(self):
        req=request();s=self.sources['T01'];self.assertTrue(normalize(s,row(),req,'raw',STAMP)['usable'])
        for fields in [dict(sggCd='26380'),dict(umdNm='다른동'),dict(jibun='84'),dict(aptNm='다른단지')]:
            out=normalize(s,row(**fields),req,'raw',STAMP)
            self.assertFalse(out['usable']);self.assertEqual(out['values']['identity_scope']['status'],'MISMATCH')
        for fields in [dict(sggCd=''),dict(jibun='')]:
            self.assertFalse(normalize(s,row(**fields),req,'raw',STAMP)['usable'])
        req['target'].pop('lot_number')
        self.assertFalse(normalize(s,row(),req,'raw',STAMP)['usable'])
    def test_pnu_hill_and_conflicting_anchors(self):
        req=request();req['target']['pnu']='1168010300100830000'
        self.assertEqual(identity(self.sources['T01'],row(),req)['status'],'MATCH')
        req['target']['pnu']='1168010300200830000'
        self.assertEqual(identity(self.sources['T01'],row(),req)['status'],'MISMATCH')
    def test_wrong_complex_cannot_be_whitelisted_by_reference_binding(self):
        req=request(['S02']);req['target'].update(pnu='1168010300100830000',kapt_code='SEOUL',legal_dong='개포동')
        req['reference_bindings']={'S02':{'kaptCode':'BUSAN'}}
        row=dict(kaptCode='BUSAN',bjdCode='2638010100',kaptAddr='부산광역시 사하구 괴정동 258')
        out=normalize(self.sources['S02'],row,req,'raw',STAMP)
        self.assertFalse(out['usable']);self.assertEqual(out['values']['identity_scope']['status'],'MISMATCH')
    def test_reference_snapshot_is_not_invented_provider_basis_date(self):
        req=request(['S02']);req['target']=dict(subject_id='public',lawd_cd='26380',
            pnu='2638010100102580000',kapt_code='A10027875',legal_dong='괴정동')
        row=dict(kaptCode='A10027875',bjdCode='2638010100',kaptAddr='부산광역시 사하구 괴정동 258 괴정 경성스마트W아파트')
        out=normalize(self.sources['S02'],row,req,'raw',STAMP)
        self.assertTrue(out['usable']);self.assertIsNone(out['provenance']['basis_date'])
        self.assertEqual(out['provenance']['basis_type'],'OBSERVED_SNAPSHOT')
        self.assertIn('PROVIDER_BASIS_DATE_NOT_SUPPLIED',out['warnings'])
    def test_regional_context_is_not_property_evidence(self):
        req=request(['S10']);req['source_scopes']={'S10':'DISTRICT_CONTEXT'}
        out=normalize(self.sources['S10'],{'signguCd':'11680'},req,'raw',STAMP)
        self.assertTrue(out['usable']);self.assertEqual(out['values']['identity_scope']['kind'],'DISTRICT_CONTEXT')
        req['source_scopes']={'S10':'PROPERTY'}
        self.assertFalse(normalize(self.sources['S10'],{'signguCd':'11680'},req,'raw',STAMP)['usable'])
    def test_transaction_month_is_checked_and_old_usable_flag_not_trusted(self):
        req=request();s=self.sources['T01'];out=normalize(s,row(dealMonth='7'),req,'raw',STAMP)
        self.assertIn('TRANSACTION_DATE_OUTSIDE_PERIOD',out['issues'])
        out['usable']=True;self.assertFalse(current_api_usable(s,out,req))
    def test_report_export_rechecks_legacy_usable_rows(self):
        from prepare_report_evidence import prepare,review_coverage
        from collector import digest,encoded
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            building=dict(sigunguCd='11680',bjdongCd='10300',bun='0083',ji='0000',platGbCd='0',
                          platPlc='서울특별시 강남구 개포동 83번지',bldNm='OFFLINE BUILDING FIXTURE')
            e=Engine(Path(directory)/'runs',Path(directory)/'cache',FakeTransport([xml([row()]),xml([building])]),{'DATA_GO_KR_SERVICE_KEY':'offline-secret'})
            req=request(['T01','S01']);req['target']['pnu']='1168010300100830000'
            req['params']={'S01':dict(sigunguCd='11680',bjdongCd='10300',bun='0083',ji='0000')}
            run,m=e.collect(req,'report')
            report=next(r for r in self.reports if r['id']=='P01')
            review=dict(run_id='report',reviews=[dict(requirement_id=g['requirement_id'],review_status='VERIFIED',
                review_note='OFFLINE coverage fixture, not live evidence',coverage={item:dict(
                    source_id='S01' if i==0 else 'T01',record_index=0,fields=['bldNm'] if i==0 else ['price_krw'])
                    for item in g['coverage_checklist']}) for i,g in enumerate(report['data_requirements'][:2])])
            file=Path(directory)/'review.json';write(file,review);review_coverage(run,file)
            self.assertEqual(load(prepare(run,'P01'))['status'],'READY_WITH_DECLARED_SCOPE')
            stored=load(run/'normalized/T01.json');stored[0]['raw_fields']['jibun']='999'
            write(run/'normalized/T01.json',stored)
            # Model an old accepted review tied to an unsafe legacy usable record.
            m=load(run/'manifest.json')
            for proof in m['requirement_reviews']['P01-D02']['proofs'].values():
                proof['record_sha256']=digest(encoded(stored[0]))
            write(run/'manifest.json',m)
            self.assertFalse(current_api_usable(self.sources['T01'],stored[0],req))
            with self.assertRaises(CollectionError):prepare(run,'P01')
            self.assertEqual(load(run/'P01-evidence.json')['records'],[])

if __name__=='__main__':unittest.main()
