import unittest, tempfile
from pathlib import Path
from test_workflow import make_case, e
import covers

class CoverTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent);self.addCleanup(self.tmp.cleanup);self.dir=Path(self.tmp.name);self.path=make_case(self.dir)
 def edit(self,fn):
  c=e.load(self.path);fn(c);e.save(self.path,c)
 def test_cover_fields_are_claim_bound(self):
  self.edit(lambda c:c.update(cover={'title':'대상 {{A}}','subtitle':'차이는 {{DIFF}}만원입니다.'}))
  out=self.dir/'bound';e.render_contract(self.path,out)
  text=(out/'report.html').read_text(encoding='utf-8')
  self.assertIn('대상 100',text);self.assertEqual(text.count('data-ezi-cover="V"'),2)
  self.edit(lambda c:c['cover'].update(title='확인되지 않은 999만원'))
  with self.assertRaisesRegex(ValueError,'NUMERIC_TEXT_UNBOUND'):e.check_contract(self.path)
 def test_disable_and_unknown_fields(self):
  self.edit(lambda c:c.update(cover={'enabled':False}))
  out=self.dir/'off';e.render_contract(self.path,out)
  self.assertNotIn('data-ezi-cover="V"',(out/'report.html').read_text(encoding='utf-8'))
  self.edit(lambda c:c['cover'].update(arbitrary_fact='ignored'))
  with self.assertRaisesRegex(ValueError,'COVER_FIELD_UNKNOWN'):e.check_contract(self.path)
 def test_all_types_and_no_apartment_assumption(self):
  for i in range(1,15):
   c=e.check_contract(make_case(self.dir/('cover'+str(i)),f'P{i:02}'))
   doc=covers.wrap_document('<html><head></head><body><p>original</p></body></html>',e.cover_metadata(c))
   self.assertEqual(doc.count('data-ezi-cover="V"'),2);self.assertIn('<p>original</p>',doc)
   self.assertNotIn('희망 입주일',doc);self.assertNotIn('담당자명',doc)
   with self.assertRaisesRegex(ValueError,'ALREADY_PRESENT'):covers.wrap_document(doc,e.cover_metadata(c))
 def test_metadata_and_brand_escape(self):
  c=e.check_contract(self.path);meta=e.cover_metadata(c);meta['title']='<script>alert("x")</script>'
  doc=covers.wrap_document('<html><head></head><body></body></html>',meta,{'business_name':'A&B','phone':'<img onerror=x>'})
  self.assertIn('A&amp;B',doc);self.assertNotIn('<script>',doc);self.assertIn('&lt;img',doc)

if __name__=='__main__':unittest.main()
