import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/collection')]
import integrations as I
import scientific_charts as C
TEST_ROOT=ROOT/'work/integration-tests'
TEST_ROOT.mkdir(parents=True,exist_ok=True)

def response(number='99',status='OK'):
 return {'ok':True,'result':{'response':{'status':status,'refined':{'text':'서울특별시 송파구 올림픽로 '+number+' (잠실엘스)'},'result':{'point':{'x':'127.08','y':'37.51'}}}}}
class IntegrationTests(unittest.TestCase):
 def test_address_full_number_and_target(self):
  expected=['서울특별시','송파구','올림픽로','99','잠실엘스']
  self.assertEqual(I.match_address(response(),expected),(127.08,37.51))
  for value in ['99-1','199','990']:
   with self.assertRaisesRegex(ValueError,'TARGET_MISMATCH'):I.match_address(response(value),expected)
  with self.assertRaises(ValueError):I.match_address(response(),['강남구','99'])
 def test_empty_and_ambiguous(self):
  with self.assertRaisesRegex(ValueError,'NO_RESULT'):I.match_address({'response':{'result':None}},['99'])
  with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):I.match_address({'response':{'result':[{},{}]}},['99'])
 def test_check_is_network_free(self):
  with patch('urllib.request.urlopen',side_effect=AssertionError('network')):
   result=I.check();self.assertFalse(result['network_called']);self.assertEqual(result['vendor_integrity'],'PASS')
 def test_status_is_not_expiry_guess(self):
  self.assertEqual(I.classify('403'),'AUTH_REJECTED');self.assertEqual(I.classify('429'),'RATE_LIMIT')
  self.assertEqual(I.classify('read timed out'),'TEMPORARY_FAILURE');self.assertEqual(I.classify('unknown'),'UNCLASSIFIED_FAILURE')
 def test_map_error_image_is_hold(self):
  with tempfile.TemporaryDirectory(dir=TEST_ROOT) as d:
   out=Path(d)/'map'
   def fake(args,key):
    if args[0]=='geocode':return json.dumps(response())
    Path(args[-1]).write_text('{"error":"AUTH"}');return '{}'
   req={'targets':[{'label':'잠실엘스','address':'서울 송파구 올림픽로 99','expected_tokens':['서울특별시','송파구','올림픽로','99','잠실엘스']}]}
   with patch.object(I,'cli',side_effect=fake):r=I.map_collect(req,out,'synthetic')
   self.assertEqual(r['status'],'HOLD');self.assertTrue((out/'map-provenance.json').is_file())
 def test_cli_retry_scope_and_secret_not_argv(self):
  import subprocess
  with tempfile.TemporaryDirectory(dir=TEST_ROOT) as d:
   exe=Path(d)/'fake.exe';exe.write_bytes(b'test')
   cfg={'vworld_release':{'assets':{I.platform.system():{'sha256':I.sha(exe)}}}}
   observed=[]
   def denied(cmd,**kwargs):observed.append(cmd);return subprocess.CompletedProcess(cmd,1,'','INVALID_KEY')
   with patch.object(I,'binary',return_value=exe),patch.object(I,'lock',return_value=cfg),patch.object(I.tempfile,'tempdir',str(TEST_ROOT)),patch.object(I.subprocess,'run',side_effect=denied):
    with self.assertRaisesRegex(ValueError,'AUTH_REJECTED'):I.cli(['geocode','주소'],'synthetic-secret')
   self.assertEqual(len(observed),1);self.assertNotIn('synthetic-secret',str(observed))
   with patch.object(I,'binary',return_value=exe),patch.object(I,'lock',return_value=cfg),patch.object(I.tempfile,'tempdir',str(TEST_ROOT)),patch.object(I.subprocess,'run',side_effect=subprocess.TimeoutExpired('fake',60)) as run,patch.object(I.time,'sleep'):
    with self.assertRaisesRegex(ValueError,'TEMPORARY_FAILURE'):I.cli(['geocode','주소'],'synthetic-secret')
    self.assertEqual(run.call_count,3)
 def test_chart_input_hash_blocks_changed_data(self):
  with tempfile.TemporaryDirectory(dir=TEST_ROOT) as d:
   p=Path(d)/'자료 공백.json';p.write_text('{"v":3}',encoding='utf-8')
   spec={'dataset':str(p),'dataset_sha256':'0'*64,'points':[{'label':'값','pointer':'/v'}]}
   with self.assertRaisesRegex(ValueError,'DATASET_CHANGED'):C.chart(spec,Path(d)/'out')
 def test_chart_missing_and_zero_remain_distinct(self):
  with tempfile.TemporaryDirectory(dir=TEST_ROOT) as d:
   p=Path(d)/'자료 공백.json';p.write_text('{"v":[0,null,3]}',encoding='utf-8')
   spec={'dataset':str(p),'dataset_sha256':I.sha(p),'kind':'line','points':[{'label':str(i),'pointer':f'/v/{i}'} for i in range(3)],'basis_date':'2026-10-10','unit':'건','scope':'synthetic_test'}
   result=C.chart(spec,Path(d)/'그래프 공백');self.assertEqual([x['value'] for x in result['points']],[0,None,3])
   self.assertTrue((Path(d)/'그래프 공백/figure.svg').exists())
   with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):C.chart(spec,Path(d)/'그래프 공백')
 def test_incomplete_map_provenance_rejected(self):
  with tempfile.TemporaryDirectory(dir=TEST_ROOT) as d:
   p=Path(d)/'map.png';p.write_bytes(b'fake');q=Path(d)/'prov.json';q.write_text(json.dumps({'status':'PASS','map_sha256':I.sha(p)}))
   a={'kind':'map','file':'map.png','sha256':I.sha(p),'provenance':'prov.json','provenance_sha256':I.sha(q),'address_review':'PASS','alt':'지도','caption':'주소'}
   with self.assertRaisesRegex(ValueError,'PROVENANCE_INCOMPLETE'):I.verify_asset(a,d,{})
if __name__=='__main__':unittest.main()
