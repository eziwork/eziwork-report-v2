import contextlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import key_environment as keys

class KeyEnvironmentTests(unittest.TestCase):
    def setUp(self):
        p=patch.object(keys,'legacy_values',return_value=({},'test-local.json'));p.start();self.addCleanup(p.stop)
    def test_presence_without_disclosure(self):
        with patch.dict(os.environ,{},clear=True),patch.object(keys,'user_values',return_value={keys.BASIC[0]:'synthetic-secret'}):
            result=keys.check()
        self.assertEqual(result['missing'],list(keys.BASIC[1:]))
        self.assertNotIn('synthetic-secret',json.dumps(result))
        self.assertFalse(result['live_call'])
    def test_setup_requests_only_missing(self):
        with patch.object(keys.platform,'system',return_value='Windows'),patch.object(keys,'check',return_value={'missing':[keys.BASIC[1]]}),patch.object(keys,'masked_input',return_value='synthetic') as prompt,patch.object(keys,'save_user') as save:
            keys.setup()
        prompt.assert_called_once();save.assert_called_once_with(keys.BASIC[1],'synthetic')
    def test_no_echo_fallback(self):
        with patch.object(keys.platform,'system',return_value='Windows'),patch.object(keys,'check',return_value={'missing':[keys.BASIC[0]]}),patch.object(keys,'masked_input',side_effect=ValueError('INTERACTIVE_SECURE_TERMINAL_REQUIRED')),patch.object(keys,'save_user') as save:
            with self.assertRaisesRegex(ValueError,'SECURE_TERMINAL'):keys.setup()
            save.assert_not_called()
    def test_windows_save_and_readback(self):
        store={}
        class Registry:
            HKEY_CURRENT_USER=1;KEY_SET_VALUE=2;REG_SZ=1;REG_EXPAND_SZ=2
            @staticmethod
            def CreateKeyEx(*args):return contextlib.nullcontext(object())
            @staticmethod
            def OpenKey(*args):return contextlib.nullcontext(object())
            @staticmethod
            def SetValueEx(handle,name,unused,kind,value):store[name]=(value,kind)
            @staticmethod
            def QueryValueEx(handle,name):
                if name not in store:raise FileNotFoundError
                return store[name]
        with patch.dict(sys.modules,{'winreg':Registry}),patch.object(keys.platform,'system',return_value='Windows'),patch.dict(os.environ,{},clear=True):
            keys.save_user(keys.BASIC[0],'synthetic')
            self.assertEqual(keys.user_values()[keys.BASIC[0]],'synthetic')
            self.assertEqual(os.environ[keys.BASIC[0]],'synthetic')
    def test_other_platform(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder,patch.object(keys.platform,'system',return_value='Darwin'),patch.object(keys,'managed_path',return_value=Path(folder)/'한글 공백/environment.json'),patch.dict(os.environ,{},clear=True):
            keys.save_user(keys.BASIC[0],'synthetic')
            self.assertEqual(keys.user_values()[keys.BASIC[0]],'synthetic')
            self.assertTrue(keys.check()['keys'][keys.BASIC[0]]['managed_store_present'])
    def test_invalid_input(self):
        for value in ['', 'secret\nsecond', 'secret value']:
            with self.assertRaisesRegex(ValueError,'EMPTY_OR_INVALID_KEY_INPUT'):keys.save_user(keys.BASIC[0],value)
if __name__=='__main__':unittest.main()
