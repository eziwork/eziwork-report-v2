from pathlib import Path
import os,sys,json,tempfile,unittest,copy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/collection'),str(ROOT/'runtime/python')]
import key_environment as keys
from collector import registry,validate_request,write,load,Engine
from evidence_rules import statistic_issues,public_issues,revalidate,digest_file,RULE_VERSION
from public_evidence import catchment,review_official_payload,public_document,collect_address
from adapters import CollectionError
from quality import normalize,validate_input
from prepare_report_evidence import prepare,current_reviews
import eziwork

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name)
        self.sources,self.reports=registry()
        self.req={'schema_version':1,'report_type':'P01','sources':['S08'],'target':{'subject_id':'test'},'basis_date':'2026-10-10',
            'params':{'S08':{'orgId':'101','tblId':'T','itmId':'I','objL1':'11','prdSe':'M','startPrdDe':'202601','endPrdDe':'202603','expected_unit':'명'}}}
        self.row={'ORG_ID':'101','TBL_ID':'T','ITM_ID':'I','C1':'11','PRD_SE':'M','PRD_DE':'202602','DT':'0','UNIT_NM':'명'}
    def test_sources_explicit(self):
        self.req.pop('sources')
        with self.assertRaisesRegex(CollectionError,'SOURCE_SELECTION_REQUIRED'):validate_request(self.req,self.sources,self.reports)
    def test_five_keys_and_no_value_disclosure(self):
        for count in (0,2,5):
            with patch.dict(os.environ,{},clear=True),patch.object(keys,'user_values',return_value={k:'SECRET' for k in keys.BASIC[:count]}),patch.object(keys,'legacy_values',return_value=({},'test')):
                result=keys.check();self.assertEqual(len(result['missing']),5-count);self.assertNotIn('SECRET',json.dumps(result))
    def test_process_priority_and_conflict(self):
        with patch.dict(os.environ,{keys.BASIC[0]:'process'},clear=True),patch.object(keys,'user_values',return_value={keys.BASIC[0]:'stored'}),patch.object(keys,'legacy_values',return_value=({},'test')):
            self.assertEqual(keys.check()['conflicts'],[keys.BASIC[0]])
            keys.apply_saved();self.assertEqual(os.environ[keys.BASIC[0]],'process')
    def test_cancel_keeps_completed_and_resumes(self):
        saved={}
        def check():return {'missing':[k for k in keys.BASIC if k not in saved]}
        with patch.object(keys,'check',side_effect=check),patch.object(keys,'legacy_values',return_value=({},'test')),patch.object(keys,'save_user',side_effect=lambda k,v:saved.update({k:v})),patch.object(keys,'masked_input',side_effect=['one',KeyboardInterrupt]):
            result=keys.setup()
        self.assertEqual(result['saved_names'],[keys.BASIC[0]]);self.assertEqual(result['missing'],list(keys.BASIC[1:]))
        with patch.object(keys,'check',side_effect=check),patch.object(keys,'legacy_values',return_value=({},'test')),patch.object(keys,'save_user',side_effect=lambda k,v:saved.update({k:v})),patch.object(keys,'masked_input',return_value='two') as prompt:
            self.assertFalse(keys.setup()['missing']);self.assertEqual(prompt.call_count,4)
    def test_migration_no_overwrite(self):
        with patch.object(keys,'check',return_value={'missing':[keys.BASIC[1]]}),patch.object(keys,'legacy_values',return_value=({keys.BASIC[0]:'a',keys.BASIC[1]:'b'},'test')),patch.object(keys,'save_user') as save,patch.object(keys,'masked_input') as prompt:
            keys.setup();save.assert_called_once_with(keys.BASIC[1],'b');prompt.assert_not_called()
    def test_storage_failure_no_success(self):
        with patch.object(keys,'check',return_value={'missing':[keys.BASIC[0]]}),patch.object(keys,'legacy_values',return_value=({},'test')),patch.object(keys,'masked_input',return_value='test'),patch.object(keys,'save_user',side_effect=OSError):
            with self.assertRaises(OSError):keys.setup()
    def test_managed_mac_persistence(self):
        path=self.dir/'한글 공백/environment.json'
        with patch.object(keys.platform,'system',return_value='Darwin'),patch.object(keys,'managed_path',return_value=path),patch.dict(os.environ,{},clear=True):
            keys.save_user(keys.BASIC[2],'synthetic');os.environ.clear()
            self.assertEqual(keys.user_values(),{keys.BASIC[2]:'synthetic'});keys.apply_saved();self.assertEqual(os.environ[keys.BASIC[2]],'synthetic')
            if os.name!='nt':self.assertEqual(path.stat().st_mode & 0o777,0o600)
    def test_new_report_gate_precedes_environment(self):
        with patch.object(sys,'argv',['eziwork','collect','--request','missing.json','--run-id','x']),patch.object(keys,'require_registered',return_value={'missing':['ECOS_API_KEY']}),patch.object(eziwork,'environment') as env:
            self.assertEqual(eziwork.main(),2);env.assert_not_called()
    def test_zero_statistic_is_valid(self):
        self.assertEqual(statistic_issues(self.sources['S08'],self.row,self.req),[])
    def test_statistic_dimensions(self):
        for key in ('ORG_ID','TBL_ID','ITM_ID','C1','PRD_SE'):
            with self.subTest(key=key):
                row={**self.row,key:'wrong'};self.assertTrue(statistic_issues(self.sources['S08'],row,self.req))
    def test_statistic_missing_not_zero(self):
        for v in (None,'-','...','NaN'):
            self.assertTrue(statistic_issues(self.sources['S08'],{**self.row,'DT':v},self.req))
    def test_period_and_cycle(self):
        for v in ('202001','20260101','2026Q1','202613'):
            self.assertTrue(statistic_issues(self.sources['S08'],{**self.row,'PRD_DE':v},self.req))
    def test_rone_quarter_and_ecos_year(self):
        req=copy.deepcopy(self.req);req['params']['S09']={'STATBL_ID':'T','ITM_ID':'I','CLS_ID':'11','DTACYCLE_CD':'Q','START_WRTTIME':'2026Q1','END_WRTTIME':'2026Q3','expected_unit':'%'}
        r={'STATBL_ID':'T','ITM_ID':'I','CLS_ID':'11','DTACYCLE_CD':'Q','WRTTIME_IDTFR_ID':'202602','DTA_VAL':'1','UI_NM':'%'}
        self.assertFalse(statistic_issues(self.sources['S09'],r,req))
        req['params']['S22']={'stat_code':'T','item_code':'I','cycle':'A','start':'2025','end':'2026','expected_unit':'%'}
        r={'STAT_CODE':'T','ITEM_CODE1':'I','CYCLE':'A','TIME':'2026','DATA_VALUE':'0','UNIT_NAME':'%'}
        self.assertFalse(statistic_issues(self.sources['S22'],r,req));r['TIME']='202601';self.assertTrue(statistic_issues(self.sources['S22'],r,req))
    def test_metadata_required_and_hash_changed(self):
        row=dict(self.row);row.pop('PRD_SE')
        self.assertTrue(statistic_issues(self.sources['S08'],row,self.req))
        path=self.dir/'metadata.json';write(path,{'PRD_SE':'M'})
        self.req['scope_evidence']={'S08':{'file':str(path),'sha256':digest_file(path),'source_url':'https://kosis.kr/','review_status':'VERIFIED','fields':{'prdSe':'M'},'field_quotes':{'prdSe':'M'}}}
        self.assertFalse(statistic_issues(self.sources['S08'],row,self.req));path.write_text('changed')
        self.assertTrue(statistic_issues(self.sources['S08'],row,self.req))
    def test_empty_replacement_rows_rejected(self):
        for sid in ('S07','S12','S17'):
            payload={'source_id':sid,'evidence_mode':'ACTUAL','review_status':'VERIFIED','source_url':'https://www.law.go.kr/','basis_date':'2026-10-10','identity':{'subject_id':'test'},'records':[{}]}
            rows,_=validate_input(self.sources[sid],payload,self.req);self.assertFalse(rows[0]['usable'])
    def school(self):
        return {'record_type':'location','school_code':'S01','school_level':'초등학교','operating_status':'운영','address':'서울특별시 송파구 학교로 1',
                'lon':127.1,'lat':37.5,'basis_date':'2026-10-10','source_url':'https://www.data.go.kr/'}
    def test_school_location_not_assignment(self):
        self.req['params']['S12']={'school_code':'S01','region':'서울특별시 송파구'}
        row=self.school();self.assertFalse(public_issues(self.sources['S12'],row,self.req))
        row['record_type']='assignment';self.assertTrue(public_issues(self.sources['S12'],row,self.req))
    def test_school_region_and_closed(self):
        row=self.school();self.req['params']['S12']={'region':'부산'}
        self.assertIn('SCHOOL_REGION_MISMATCH',public_issues(self.sources['S12'],row,self.req))
        row['operating_status']='폐교';self.assertIn('SCHOOL_NOT_ACTIVE',public_issues(self.sources['S12'],row,self.req))
    def test_final_notice_and_year_required(self):
        row={**self.school(),'record_type':'assignment','academic_year':2026,'notice_status':'PRELIMINARY','notice_url':'https://sen.go.kr/a','notice_sha256':'hash','exception_conditions':[],'geometry_result':{'status':'UNIQUE_INTERIOR','school_codes':['S01'],'target_id':'test'}}
        self.req['params']['S12']={'academic_year':2027}
        issues=public_issues(self.sources['S12'],row,self.req);self.assertIn('FINAL_NOTICE_REQUIRED',issues);self.assertIn('SCHOOL_YEAR_MISMATCH',issues)
    def test_law_scope_and_future(self):
        row={'law_name':'법','article':'제1조','law_body':'테스트 조문','effective_date':'2026-01-01','jurisdiction':'전국','source_url':'https://www.law.go.kr/','basis_date':'2026-10-10','addenda_review':'REVIEWED','annex_review':'NONE_IN_SOURCE'}
        self.req['params']['S17']={'expected_law_name':'법','expected_article':'제1조','expected_jurisdiction':'전국'}
        self.assertFalse(public_issues(self.sources['S17'],row,self.req))
        for key,bad in [('effective_date','2099-01-01'),('article','제2조'),('jurisdiction','서울')]:
            self.assertTrue(public_issues(self.sources['S17'],{**row,key:bad},self.req))
    def geometry(self,crs='EPSG:4326'):
        coords=[[127,37],[128,37],[128,38],[127,38],[127,37]]
        if crs!='EPSG:4326':
            from pyproj import Transformer
            tr=Transformer.from_crs('EPSG:4326',crs,always_xy=True);coords=[list(tr.transform(*p)) for p in coords]
        geo=self.dir/'geo.json';join=self.dir/'join.json'
        write(geo,{'type':'FeatureCollection','features':[{'type':'Feature','properties':{'zone_id':'Z'},'geometry':{'type':'Polygon','coordinates':[coords]}}]})
        write(join,{'Z':['S01']})
        return {'geometry_file':geo.name,'join_file':join.name,'geometry_sha256':digest_file(geo),'join_sha256':digest_file(join),'source_crs':crs,'source_url':'https://schoolzone.emac.kr/','basis_date':'2026-10-10','target_id':'test','lon':127.5,'lat':37.5}
    def test_geometry_crs(self):
        for crs in ('EPSG:4326','EPSG:5179'):
            self.assertEqual(catchment(self.geometry(crs),self.dir)['status'],'UNIQUE_INTERIOR')
    def test_geometry_boundary_multiple_and_none(self):
        s=self.geometry();s['lon']=127;self.assertEqual(catchment(s,self.dir)['status'],'BOUNDARY')
        s['lon']=126;self.assertEqual(catchment(s,self.dir)['status'],'NO_MATCH')
        s['lon']=127.5;write(self.dir/'join.json',{'Z':['S01','S02']});s['join_sha256']=digest_file(self.dir/'join.json')
        self.assertEqual(catchment(s,self.dir)['status'],'MULTIPLE')
    def test_geometry_changed_original(self):
        s=self.geometry();(self.dir/'geo.json').write_text('{}')
        with self.assertRaisesRegex(CollectionError,'HASH_MISMATCH'):catchment(s,self.dir)
    def test_public_contact_separate_from_customer(self):
        path=self.dir/'source.txt';path.write_text('S01 서울 학교 담당부서 office@example.invalid',encoding='utf-8')
        sha=digest_file(path);row={**self.school(),'address':'서울 학교','original_proof':{'raw_sha256':sha,'review_status':'VERIFIED','field_quotes':{'school_code':'S01','address':'서울 학교'}}}
        p={'source_id':'S12','data_format_version':2,'intake_channel':'OFFICIAL_PUBLIC','source_url':'https://www.data.go.kr/','records':[row],'attachments':[{'file':path.name,'source_url':'https://www.data.go.kr/','sha256':sha}]}
        with self.assertRaisesRegex(CollectionError,'UNREVIEWED_PUBLIC_CONTACT'):review_official_payload(p,self.dir,self.req)
        p['public_contact_review']=[{'raw_sha256':sha,'value':'office@example.invalid','institutional_public_contact':True,'review_note':'원문의 공개 담당부서 이메일 확인'}]
        review_official_payload(p,self.dir,self.req)
        self.assertIn('EMAIL',eziwork.privacy_issues(path))
    def test_official_missing_original(self):
        with self.assertRaises(CollectionError):review_official_payload({'source_id':'S17','data_format_version':2,'intake_channel':'OFFICIAL_PUBLIC','source_url':'https://www.law.go.kr/','records':[{}]},self.dir,self.req)
    def test_unsupported_official_format(self):
        p=self.dir/'test.hwp';p.write_text('test')
        with self.assertRaisesRegex(CollectionError,'UNSUPPORTED_FORMAT'):public_document(p,'https://www.law.go.kr/',self.dir/'out')
    def test_unknown_source_does_not_crash(self):
        run=self.dir/'run';write(run/'request.json',self.req)
        write(run/'manifest.json',{'sources':{'OLD99':{'usable_count':1,'complete':True}},'run_id':'test'})
        with self.assertRaisesRegex(CollectionError,'REPORT_REQUIRED_DATA_MISSING'):prepare(run,'P01')
        self.assertEqual(load(run/'P01-evidence.json')['status'],'HOLD')
    def test_old_rule_approval_stale(self):
        run=self.dir/'run';write(run/'request.json',self.req)
        m={'sources':{},'requirement_reviews':{'x':{'review_status':'VERIFIED','proofs':{},'validation_rule_version':'2.2.0'}}}
        self.assertEqual(current_reviews(run,m)['requirement_reviews']['x']['review_status'],'STALE')
    def test_legacy_source_snapshot(self):
        old,_=registry('2.2.0');self.assertEqual(old['S07']['credential'],'JUSO_CONFM_KEY')
        self.assertEqual(self.sources['S07']['credential'],'VWORLD_API_KEY')
        self.assertFalse(revalidate(self.sources['S17'],{'usable':True,'values':{},'provenance':{}},self.req))
    def test_address_mismatch(self):
        row={'address':'서울 송파구','road_address':'서울 송파구 올림픽로 99','parcel_address':'서울 송파구 잠실동 19','lon':127.1,'lat':37.5,'expected_tokens':['송파구','99'],'basis_date':'2026-10-10','location_kind':'address_lookup_point'}
        self.req['params']['S07']={'expected_tokens':['송파구','99']}
        self.assertFalse(public_issues(self.sources['S07'],row,self.req))
        row['road_address']='부산 올림픽로 999';self.assertIn('ADDRESS_TARGET_MISMATCH',public_issues(self.sources['S07'],row,self.req))
    def test_address_cli_error_and_multiple(self):
        import integrations
        run=self.dir/'run';write(run/'request.json',self.req)
        for error in ('VWORLD_AUTH_REJECTED','VWORLD_NO_RESULT','VWORLD_AMBIGUOUS_CANDIDATES'):
            with patch.object(integrations,'cli',side_effect=ValueError(error)):
                out=collect_address(self.sources['S07'],{'address':'서울','expected_tokens':['서울']},run,'synthetic')
                self.assertFalse(out['complete']);self.assertIsNone(out['returned_count']);self.assertEqual(out['error'],error)
    def test_rule_or_raw_mutation_revokes_record(self):
        raw=self.dir/'raw.txt';raw.write_text('source')
        record=normalize(self.sources['S08'],self.row,self.req,'raw.txt','2026-10-10T00:00:00+00:00')
        record['provenance']['raw_sha256']=digest_file(raw)
        self.assertTrue(revalidate(self.sources['S08'],record,self.req,self.dir))
        changed=copy.deepcopy(record);changed['values']['DT']='999';self.assertFalse(revalidate(self.sources['S08'],changed,self.req,self.dir))
        raw.write_text('changed');self.assertFalse(revalidate(self.sources['S08'],record,self.req,self.dir))

    def test_school_explicit_target_required(self):
        self.assertIn('SCHOOL_EXPLICIT_TARGET_REQUIRED',public_issues(self.sources['S12'],self.school(),self.req))
    def test_unknown_format_rejected(self):
        record=normalize(self.sources['S08'],self.row,self.req,'raw.txt','2026-10-10')
        record['provenance']['data_format_version']=999
        self.assertFalse(revalidate(self.sources['S08'],record,self.req))
    def test_statistic_unit_mismatch(self):
        self.assertIn('STATISTIC_UNIT_MISMATCH',statistic_issues(self.sources['S08'],{**self.row,'UNIT_NM':'억원'},self.req))
    def test_mac_preserves_other_settings(self):
        path=self.dir/'environment.json';write(path,{'unrelated':'keep','LAW_OC':'old'})
        if os.name!='nt':path.chmod(0o600)
        with patch.object(keys.platform,'system',return_value='Darwin'),patch.object(keys,'managed_path',return_value=path),patch.dict(os.environ,{},clear=True):
            keys.save_user(keys.BASIC[0],'synthetic')
        self.assertEqual(load(path)['unrelated'],'keep');self.assertEqual(load(path)['LAW_OC'],'old')
    def test_actual_legacy_dataset_requires_review(self):
        ds=self.dir/'data.json';write(ds,{'status':'READY_WITH_DECLARED_SCOPE','report_id':'P01','target':{'subject_id':'test'},'records':[]})
        contract=self.dir/'contract.json';write(contract,{'schema_version':1,'report_id':'P01','mode':'actual','question':'질문','basis_date':'2026-10-10','scope':'범위','target':{'subject_id':'test'},'dataset':ds.name,'dataset_sha256':digest_file(ds)})
        with self.assertRaisesRegex(ValueError,'EVIDENCE_CURRENT_REVIEW_REQUIRED'):eziwork.check_contract(contract)

if __name__=='__main__':unittest.main()

