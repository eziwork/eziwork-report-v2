from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import eziwork as e
import key_environment as keys
import key_input
import key_window
import report_job as jobs
from delivery import file_hash, seal_output, check_receipt
from test_workflow import make_case
from test_delivery import pdf_fixture


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.store = {}
        self.saved = patch.object(keys, 'user_values', side_effect=lambda names=keys.BASIC: {k:v for k,v in self.store.items() if k in names})
        self.saved.start(); self.addCleanup(self.saved.stop)
        self.legacy = patch.object(keys, 'legacy_values', return_value=({}, 'synthetic'))
        self.legacy.start(); self.addCleanup(self.legacy.stop)

    def test_process_values_persist_without_retyping(self):
        os.environ.update({k:'synthetic-'+k for k in keys.BASIC})
        self.assertEqual(len(keys.check()['not_persistent']), 5)
        with patch.object(keys, 'save_user', side_effect=lambda k,v:self.store.update({k:v})), patch.object(keys, 'masked_input', side_effect=AssertionError('No prompt')):
            keys.ensure()
        os.environ.clear()
        self.assertFalse(keys.check()['missing'])

    def test_legacy_migration_then_window_only_for_missing(self):
        with patch.object(keys, 'legacy_values', return_value=({keys.BASIC[0]:'synthetic'}, 'synthetic')), patch.object(keys, 'save_user', side_effect=lambda k,v:self.store.update({k:v})), patch.object(key_window, 'open_window', return_value={'window_opened':True}) as window:
            self.assertTrue(keys.ensure()['window_opened'])
            window.assert_called_once()
        self.assertIn(keys.BASIC[0], self.store)

    def test_all_saved_never_opens_window(self):
        self.store.update({k:'synthetic' for k in keys.BASIC})
        with patch.object(key_window, 'open_window', side_effect=AssertionError('No window')):
            self.assertFalse(keys.ensure()['missing'])

    def test_explicit_replace_is_not_skipped(self):
        self.store['ECOS_API_KEY']='old-synthetic'
        with patch.object(keys,'save_user',side_effect=lambda k,v:self.store.update({k:v})),patch.object(keys,'masked_input',return_value='new-synthetic') as prompt:
            result=keys.setup('ECOS_API_KEY',replace=True)
        self.assertEqual(self.store['ECOS_API_KEY'],'new-synthetic')
        self.assertEqual(result['saved_names'],['ECOS_API_KEY'])
        prompt.assert_called_once()

    def test_windows_launcher_contains_no_key(self):
        os.environ['ECOS_API_KEY']='SECRET-DO-NOT-LOG'
        with patch.object(key_window.platform,'system',return_value='Windows'),patch.object(key_window.subprocess,'Popen') as popen:
            popen.return_value.pid=123
            result=key_window.open_window()
        self.assertEqual(result['status'],'INPUT_WINDOW_OPENED')
        self.assertNotIn('SECRET-DO-NOT-LOG',str(popen.call_args))
        self.assertEqual(popen.call_args.kwargs['creationflags'],getattr(key_window.subprocess,'CREATE_NEW_CONSOLE',0x10))

    def test_mac_launcher_shell_quotes_paths(self):
        with patch.object(key_window.platform,'system',return_value='Darwin'),patch.object(key_window.sys,'executable',"/tmp/a b/py'thon"),patch.object(key_window.subprocess,'run') as run:
            key_window.open_window()
        command=run.call_args.args[0]
        self.assertEqual(command[:2],['osascript','-e'])
        self.assertIn('do script',command[2])
        self.assertTrue(run.call_args.kwargs['check'])

    def test_masked_input_paste_backspace_never_echoes_secret(self):
        import types
        console=StringIO()
        console.isatty=lambda:True
        fake=types.SimpleNamespace(getwch=iter('SYNTHETICx\b\r').__next__)
        with patch.object(key_input.os,'name','nt'),patch.object(key_input.sys,'stdin',console),patch.object(key_input.sys,'stdout',console),patch.dict(sys.modules,{'msvcrt':fake}):
            value=key_input.masked_input('KEY: ')
        self.assertEqual(value,'SYNTHETIC')
        self.assertNotIn('SYNTHETIC',console.getvalue())
        self.assertIn('9 characters',console.getvalue())
        self.assertIn('Input received',console.getvalue())

    def test_masked_input_refuses_pipes(self):
        with patch.object(key_input.sys,'stdin',StringIO()):
            with self.assertRaisesRegex(ValueError,'SECURE_TERMINAL'):key_input.masked_input('KEY')


class ReportJobTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'한글 공백';self.contract=make_case(self.root)
        self.request=self.root/'request.json';self.job=self.root/'job.json'
        c=e.load(self.contract)
        e.save(self.request,{'report_type':c['report_id'],'target':{},'question':c['question']})
        jobs.start(self.request,self.job,'synthetic_test')
        self.html=self.root/'output.html';self.pdf=self.root/'output.pdf'
        self.html.write_text('<html><body>합성 100</body></html>',encoding='utf-8');pdf_fixture(self.pdf)

    def bind(self):
        return jobs.bind(self.job,self.contract,e.check_contract(self.contract))

    def seal(self):
        return seal_output(self.html,self.pdf,self.contract,file_hash(self.html),file_hash(self.contract))

    def test_research_and_contract_are_not_completed(self):
        self.assertFalse(jobs.status(self.job)['complete'])
        self.assertEqual(self.bind()['status'],'OUTPUT_REQUIRED')

    def test_finish_and_resume_check_current_files(self):
        self.bind();self.seal()
        self.assertTrue(jobs.finish(self.job,self.html,self.pdf,True)['complete'])
        self.html.write_text('<html><body>수정 200</body></html>',encoding='utf-8')
        self.assertFalse(jobs.status(self.job)['complete'])
        self.assertEqual(jobs.status(self.job)['status'],'OUTPUT_REBUILD_REQUIRED')

    def test_wrong_request_contract_rejected(self):
        c=e.check_contract(self.contract);c['question']='다른 질문'
        with self.assertRaisesRegex(ValueError,'REQUEST_MISMATCH'):jobs.bind(self.job,self.contract,c)

    def test_changed_request_requires_new_version(self):
        data=e.load(self.request);data['question']='변경';e.save(self.request,data)
        with self.assertRaisesRegex(ValueError,'REQUEST_CHANGED'):jobs.status(self.job)

    def test_unsealed_files_and_unreviewed_finish_fail(self):
        self.bind()
        with self.assertRaisesRegex(ValueError,'REVIEW_REQUIRED'):jobs.finish(self.job,self.html,self.pdf)
        with self.assertRaisesRegex(ValueError,'RECEIPT_REQUIRED'):jobs.finish(self.job,self.html,self.pdf,True)

    def test_different_html_pdf_and_contract_rejected(self):
        self.bind();self.seal()
        other=self.root/'other.html';other.write_text('<html><body>다른 200</body></html>',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'FILES_CHANGED'):check_receipt(other,self.pdf,self.contract)
        self.contract.write_text(self.contract.read_text(encoding='utf-8')+' ',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'CONTRACT_MISMATCH'):check_receipt(self.html,self.pdf,self.contract)

    def test_render_input_race_rejected(self):
        with self.assertRaisesRegex(ValueError,'HTML_CHANGED'):seal_output(self.html,self.pdf,self.contract,'old',file_hash(self.contract))


if __name__=='__main__':unittest.main()
