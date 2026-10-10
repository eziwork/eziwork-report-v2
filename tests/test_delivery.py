from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import eziwork
from delivery import check_delivery
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def pdf_fixture(path, text=True, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if text:
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 20 200 Td (Synthetic report 100) Tj ET')
        page[NameObject('/Contents')] = stream
    if encrypted:
        writer.encrypt('synthetic-test-password')
    writer.write(path)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / 'tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / '한글 공백 출력'
        self.root.mkdir()
        self.html = self.root / 'report.html'
        self.pdf = self.root / 'report.pdf'
        self.html.write_text('<!doctype html><html><body>합성 보고서 100</body></html>', encoding='utf-8')
        pdf_fixture(self.pdf)

    def cli(self, *args):
        out = StringIO()
        with patch.object(sys, 'argv', ['eziwork', *map(str, args)]), redirect_stdout(out):
            code = eziwork.main()
        return code, json.loads(out.getvalue())

    def test_readable_pair_and_no_key_gate(self):
        before = (self.html.read_bytes(), self.pdf.read_bytes())
        with patch.object(eziwork.key_environment, 'require_registered', side_effect=AssertionError('Must be offline')):
            code, result = self.cli('delivery-check', '--html', self.html, '--pdf', self.pdf)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'DELIVERY_FILES_READY')
        self.assertEqual(result['pdf_pages'], 1)
        self.assertEqual(result['scope'], 'FILE_READABILITY_ONLY')
        self.assertEqual(result['files']['pdf']['sha256'], eziwork.sha(self.pdf))
        self.assertEqual(before, (self.html.read_bytes(), self.pdf.read_bytes()))

    def test_missing_either_file_cannot_complete(self):
        for flag in ('--html', '--pdf'):
            args = ['delivery-check', '--html', self.html, '--pdf', self.pdf]
            args[args.index(flag) + 1] = self.root / 'missing'
            code, result = self.cli(*args)
            self.assertEqual(code, 2)
            self.assertEqual(result['status'], 'ACTION_REQUIRED')
            self.assertIn('MISSING', result['code'])

    def test_empty_files(self):
        for path in (self.html, self.pdf):
            before = path.read_bytes()
            path.write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'EMPTY'):
                check_delivery(self.html, self.pdf)
            path.write_bytes(before)

    def test_html_requires_body_not_script_or_style(self):
        for text in ('<html></html>', '<body><script>100</script><style>body{}</style></body>', '<body><template>100</template></body>'):
            self.html.write_text(text, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'HTML_BODY_REQUIRED'):
                check_delivery(self.html, self.pdf)

    def test_invalid_html_encoding(self):
        self.html.write_bytes(b'\xff\xfe')
        with self.assertRaisesRegex(ValueError, 'HTML_INVALID'):
            check_delivery(self.html, self.pdf)

    def test_broken_blank_and_encrypted_pdf(self):
        for mode in ('broken', 'blank', 'encrypted'):
            if mode == 'broken':
                self.pdf.write_bytes(b'not a PDF')
            else:
                pdf_fixture(self.pdf, text=mode != 'blank', encrypted=mode == 'encrypted')
            with self.assertRaisesRegex(ValueError, 'PDF_INVALID_OR_NO_TEXT'):
                check_delivery(self.html, self.pdf)

    def test_recheck_uses_current_files_not_old_success(self):
        first = check_delivery(self.html, self.pdf)
        self.html.write_text('<html><body>수정본 200</body></html>', encoding='utf-8')
        second = check_delivery(self.html, self.pdf)
        self.assertNotEqual(first['files']['html']['sha256'], second['files']['html']['sha256'])
        self.pdf.unlink()
        with self.assertRaisesRegex(ValueError, 'PDF_MISSING'):
            check_delivery(self.html, self.pdf)

    def test_pdf_command_does_not_trust_renderer_exit_only(self):
        self.pdf.unlink()
        with patch.object(eziwork, 'node', return_value='node'), patch.object(eziwork.subprocess, 'run'):
            code, result = self.cli('pdf', '--input', self.html, '--output', self.pdf)
        self.assertEqual(code, 2)
        self.assertEqual(result['code'], 'DELIVERY_PDF_MISSING')

    def test_render_pdf_checks_files_and_html_only_is_supported(self):
        contract = self.root / 'contract.json'
        contract.write_text('{"mode":"synthetic_test"}', encoding='utf-8')
        with patch.object(eziwork, 'render_contract', return_value=self.html), patch.object(eziwork, 'node', return_value='node'), patch.object(eziwork.subprocess, 'run'):
            code, result = self.cli('render', '--contract', contract, '--output', self.root, '--pdf')
            self.assertEqual((code, result['status']), (0, 'DELIVERY_FILES_READY'))
            self.pdf.unlink()
            code, result = self.cli('render', '--contract', contract, '--output', self.root, '--pdf')
            self.assertEqual((code, result['code']), (2, 'DELIVERY_PDF_MISSING'))
            code, result = self.cli('render', '--contract', contract, '--output', self.root)
            self.assertEqual((code, result['status']), (0, 'HTML_ONLY'))


if __name__ == '__main__':
    unittest.main()
