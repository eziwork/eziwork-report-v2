from pathlib import Path
import sys,json,tempfile,unittest,os
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import eziwork as e

def make_case(directory,report='P01'):
 d=Path(directory);d.mkdir(parents=True,exist_ok=True)
 data={'status':'SYNTHETIC_TEST','report_id':report,'records':[{'source_id':'TEST','usable':True,'values':{'price':100,'cost':70,'zero':0}}]}
 e.save(d/'data.json',data)
 c={'schema_version':1,'report_id':report,'mode':'synthetic_test','title':'다른 지역 검증용 사례','question':'합성 비교 대상의 금액 차이는 얼마인가요?','basis_date':'2026-10-10','scope':'가상값으로 실행 경로를 시험합니다.','dataset':'data.json','dataset_sha256':e.sha(d/'data.json'),'sources':[{'id':'TEST','title':'합성 검증 자료','url':'provided:synthetic','basis_date':'2026-10-10'}], 'claims':[{'id':'A','source_ids':['TEST'],'record_index':0,'field':'price','value':100},{'id':'B','source_ids':['TEST'],'record_index':0,'field':'cost','value':70},{'id':'DIFF','source_ids':['TEST'],'operation':'difference','inputs':['A','B'],'value':30}], 'blocks':[{'id':'answer','title':'두 금액의 차이는 {{DIFF}}만원입니다.','paragraphs':['{{A}}만원과 {{B}}만원을 비교한 합성 테스트입니다. 실제 매물 가격이 아닙니다.'],'claim_ids':['A','B','DIFF'],'highlights':['합성 테스트'],'figure_ids':['prices']}], 'figures':[{'id':'prices','type':'bar','title':'합성 금액 비교','unit':'만원','points':[{'label':'가상 대상 가','claim_id':'A','value':100},{'label':'가상 대상 나','claim_id':'B','value':70}]}],'qa':{'evidence_review':'PASS','copy_review':'PASS'}}
 e.save(d/'report.json',c);return d/'report.json'

class WorkflowTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent);self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name)/'한글 공백 경로';self.path=make_case(self.dir)
 def edit(self,fn):c=e.load(self.path);fn(c);e.save(self.path,c)
 def test_all_14_render_and_immutable_revision(self):
  for i in range(1,15):
   p=make_case(self.dir/str(i),f'P{i:02}');out=p.parent/'v01';e.render_contract(p,out)
   self.assertIn('합성 검증 예시',(out/'report.html').read_text(encoding='utf-8'))
   with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):e.render_contract(p,out)
 def test_changed_dataset_fails(self):
  with (self.dir/'data.json').open('a') as f:f.write(' ')
  with self.assertRaisesRegex(ValueError,'DATASET_CHANGED'):e.check_contract(self.path)
 def external_asset(self):
  p=self.dir/'chart.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="30"><text x="0" y="20">100</text></svg>',encoding='utf-8')
  q=self.dir/'provenance.json';e.save(q,{'status':'PASS','points':[{'label':'가상 대상','value':100}],'unit':'만원','output_sha256':{'svg':e.sha(p)}})
  a={'id':'external','kind':'chart','file':p.name,'sha256':e.sha(p),'provenance':q.name,'provenance_sha256':e.sha(q),'unit':'만원','points':[{'label':'가상 대상','claim_id':'A'}],'alt':'합성 금액','caption':'금액은 {{A}}만원입니다.'}
  self.edit(lambda c:(c.update(assets=[a]),c['blocks'][0].update(asset_ids=['external'])))
  return a,q
 def test_external_asset_render_and_provenance(self):
  a,q=self.external_asset();out=e.render_contract(self.path,self.dir/'external-output')
  self.assertIn('data:image/svg+xml;base64,',out.read_text(encoding='utf-8'))
  r=e.load(q);r['points'][0]['value']=999;e.save(q,r)
  self.edit(lambda c:c['assets'][0].update(provenance_sha256=e.sha(q)))
  with self.assertRaisesRegex(ValueError,'ASSET_DATA_MISMATCH'):e.check_contract(self.path)
 def test_external_asset_unbound_text_and_units(self):
  a,q=self.external_asset()
  for field in ['caption','alt']:
   self.edit(lambda c:c['assets'][0].update({field:'999만원'}))
   with self.assertRaisesRegex(ValueError,'NUMERIC_TEXT_UNBOUND'):e.check_contract(self.path)
   self.edit(lambda c:c['assets'][0].update({field:a[field]}))
  d=e.load(self.dir/'data.json');d['records'][0]['units']={'price':'KRW','cost':'KRW'};e.save(self.dir/'data.json',d)
  self.edit(lambda c:(c.update(dataset_sha256=e.sha(self.dir/'data.json')),c['figures'][0].update(unit='원')))
  with self.assertRaisesRegex(ValueError,'ASSET_UNIT_MISMATCH'):e.check_contract(self.path)
 def test_wrong_chart_value_fails(self):
  self.edit(lambda c:c['figures'][0]['points'][0].update(value=999))
  with self.assertRaisesRegex(ValueError,'CHART_VALUE'):e.check_contract(self.path)
 def test_wrong_chart_unit_fails(self):
  d=e.load(self.dir/'data.json');d['records'][0]['units']={'price':'KRW','cost':'KRW'};e.save(self.dir/'data.json',d);self.edit(lambda c:c.update(dataset_sha256=e.sha(self.dir/'data.json')))
  with self.assertRaisesRegex(ValueError,'CHART_UNIT_MISMATCH'):e.check_contract(self.path)
 def test_wrong_fact_and_negative_index_fail(self):
  self.edit(lambda c:c['claims'][0].update(value=999))
  with self.assertRaisesRegex(ValueError,'CLAIM_VALUE'):e.check_contract(self.path)
  self.edit(lambda c:c['claims'][0].update(value=100,record_index=-1))
  with self.assertRaisesRegex(ValueError,'RECORD_INDEX'):e.check_contract(self.path)
 def test_wrong_calculation_fails(self):
  self.edit(lambda c:c['claims'][2].update(value=31))
  with self.assertRaisesRegex(ValueError,'CALCULATION_MISMATCH'):e.check_contract(self.path)
 def test_wrong_calculation_source_fails(self):
  def change(c):
   c['sources'].append({'id':'OTHER','title':'다른 합성 출처','url':'provided:other','basis_date':'2026-10-10'});c['claims'][2]['source_ids']=['OTHER']
  self.edit(change)
  with self.assertRaisesRegex(ValueError,'CALCULATION_SOURCE_MISMATCH'):e.check_contract(self.path)
 def test_missing_qa_fails(self):
  self.edit(lambda c:c.update(qa={}))
  with self.assertRaisesRegex(ValueError,'REVIEW_REQUIRED'):e.check_contract(self.path)
 def test_missing_usable_and_source_fail(self):
  d=e.load(self.dir/'data.json');d['records'][0]['usable']=False;e.save(self.dir/'data.json',d);self.edit(lambda c:c.update(dataset_sha256=e.sha(self.dir/'data.json')))
  with self.assertRaisesRegex(ValueError,'RECORD_NOT_USABLE'):e.check_contract(self.path)
 def test_hold_and_actual_target(self):
  self.edit(lambda c:c.update(mode='actual'))
  with self.assertRaisesRegex(ValueError,'EVIDENCE_NOT_READY'):e.check_contract(self.path)
  d=e.load(self.dir/'data.json');d.update(status='READY_WITH_DECLARED_SCOPE',target={'subject_id':'A'});e.save(self.dir/'data.json',d);self.edit(lambda c:c.update(dataset_sha256=e.sha(self.dir/'data.json'),target={'subject_id':'B'}))
  with self.assertRaisesRegex(ValueError,'TARGET_MISMATCH'):e.check_contract(self.path)
 def test_privacy_signals_and_redacted_summary(self):
  p=self.dir/'private.json';e.save(p,{'tenant_name':'가상 인물','phone':'010-0000-0000'});self.assertTrue(e.privacy_issues(p))
  e.save(p,{'unit_code':'A세대','rent_krw':100000});self.assertEqual([],e.privacy_issues(p))
 def test_branding_and_html_escape(self):
  p=self.dir/'brand.json';e.save(p,{'business_name':'테스트 부동산','contact_name':'담당자','phone':'상담 연락처'})
  self.edit(lambda c:c['blocks'][0]['paragraphs'].append('<script>alert("test")</script>'))
  e.render_contract(self.path,self.dir/'brand-output',p);t=(self.dir/'brand-output/report.html').read_text(encoding='utf-8');self.assertIn('테스트 부동산',t);self.assertNotIn('<script>',t)
 def test_partial_revision_and_logo_keep_previous_version(self):
  import base64
  logo=self.dir/'logo.png';logo.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aOioAAAAASUVORK5CYII='))
  brand=self.dir/'brand.json';e.save(brand,{'business_name':'합성 업무 상호','contact_name':'합성 담당','phone':'업무 연락처','logo':'logo.png'})
  first=e.render_contract(self.path,self.dir/'v01',brand);before=e.sha(first)
  d=e.load(self.dir/'data.json');d['records'][0]['values']['price']=120;e.save(self.dir/'data.json',d)
  def revise(c):
   c['dataset_sha256']=e.sha(self.dir/'data.json');c['claims'][0]['value']=120;c['claims'][2]['value']=50;c['figures'][0]['points'][0]['value']=120
  self.edit(revise);second=e.render_contract(self.path,self.dir/'v02',brand);text=second.read_text(encoding='utf-8')
  self.assertEqual(before,e.sha(first));self.assertIn('50만원',text);self.assertIn('120',text);self.assertIn('data:image/png;base64,',text);self.assertIn('합성 담당',text)
 def test_personal_key_precedence_and_disable(self):
  p=self.dir/'local.json';e.save(p,{'DATA_GO_KR_SERVICE_KEY':'local-test-value','TYPESAFE_API_KEY':'must-not-load'})
  with patch.dict(os.environ,{'EZIWORK_DISABLE_BUNDLED_KEYS':'1','EZIWORK_CREDENTIAL_FILE':str(p),'DATA_GO_KR_SERVICE_KEY':'env-test-value'}):
   c=e.credentials();self.assertEqual(c['DATA_GO_KR_SERVICE_KEY'],'env-test-value');self.assertNotIn('TYPESAFE_API_KEY',c)
 def test_unbound_customer_number_fails(self):
  self.edit(lambda c:c['blocks'][0].update(paragraphs=['금액은 999억원입니다.']))
  with self.assertRaisesRegex(ValueError,'NUMERIC_TEXT_UNBOUND'):e.check_contract(self.path)
 def test_unbound_chart_caption_fails(self):
  self.edit(lambda c:c['figures'][0].update(note='금액은 999억원입니다.'))
  with self.assertRaisesRegex(ValueError,'NUMERIC_TEXT_UNBOUND'):e.check_contract(self.path)
 def test_cp949_privacy_scan(self):
  p=self.dir/'korean.csv';p.write_bytes('호실,임대료\n가세대,500000\n'.encode('cp949'))
  self.assertEqual([],e.privacy_issues(p))
  p.write_bytes('연락처\n010-0000-0000\n'.encode('cp949'));self.assertIn('PERSONAL_CONTACT',e.privacy_issues(p))
 def test_attachment_rejected_before_copy(self):
  from prepare_input import prepare
  p=self.dir/'personal.json';e.save(p,{'phone':'010-0000-0000'});dest=self.dir/'received'
  with self.assertRaises(e.CollectionError):prepare('M03',[p],dest,privacy_reviewed=True)
  self.assertFalse(dest.exists())
 def test_atomic_replace_preserves_old_file_on_failure(self):
  p=self.dir/'atomic.json';e.save(p,{'old':1})
  with patch.object(e.collector.os,'replace',side_effect=PermissionError('test')):
   with self.assertRaises(PermissionError):e.save(p,{'new':2})
  self.assertEqual(e.load(p),{'old':1});self.assertFalse(list(self.dir.glob('*.tmp')))
 @unittest.skipUnless(os.name=='nt','Windows sharing-lock reproduction')
 def test_real_windows_lock_preserves_file(self):
  import ctypes
  from ctypes import wintypes
  p=self.dir/'locked.json';e.save(p,{'old':1});k=ctypes.WinDLL('kernel32',use_last_error=True)
  k.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];k.CreateFileW.restype=wintypes.HANDLE
  k.CloseHandle.argtypes=[wintypes.HANDLE];k.CloseHandle.restype=wintypes.BOOL
  handle=k.CreateFileW(str(p),0x80000000,1,None,3,0,None)
  self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
  try:
   with self.assertRaises(PermissionError):e.save(p,{'new':2})
  finally:k.CloseHandle(handle)
  self.assertEqual(e.load(p),{'old':1});self.assertFalse(list(self.dir.glob('*.tmp')))
 @unittest.skipUnless(os.name=='nt','Windows sharing-lock reproduction')
 def test_real_windows_temporary_lock_recovers(self):
  import ctypes,threading
  from ctypes import wintypes
  p=self.dir/'temporary-lock.json';e.save(p,{'old':1});k=ctypes.WinDLL('kernel32',use_last_error=True)
  k.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];k.CreateFileW.restype=wintypes.HANDLE
  k.CloseHandle.argtypes=[wintypes.HANDLE];handle=k.CreateFileW(str(p),0x80000000,1,None,3,0,None)
  self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
  timer=threading.Timer(.12,lambda:k.CloseHandle(handle));timer.start()
  try:e.save(p,{'new':2})
  finally:timer.join()
  self.assertEqual(e.load(p),{'new':2})

if __name__=='__main__':unittest.main()
