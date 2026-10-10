"""Read-only output checks. File readiness is not evidence or visual approval."""
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path


class BodyText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.body = False
        self.closed = False
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'body':
            self.body = True
        if tag in ('script', 'style', 'template'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag == 'body':
            self.body = False
            self.closed = True
        if tag in ('script', 'style', 'template'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if self.body and not self.hidden:
            self.parts.append(data.strip())


def check_delivery(html_path, pdf_path):
    """Check current bytes each time, without API calls or output mutation."""
    paths = {'html': Path(html_path).resolve(), 'pdf': Path(pdf_path).resolve()}
    payloads = {}
    for kind, path in paths.items():
        if not path.is_file():
            raise ValueError(f'DELIVERY_{kind.upper()}_MISSING')
        payloads[kind] = path.read_bytes()
        if not payloads[kind]:
            raise ValueError(f'DELIVERY_{kind.upper()}_EMPTY')
    parser = BodyText()
    try:
        parser.feed(payloads['html'].decode('utf-8-sig'))
        parser.close()
    except (UnicodeError, ValueError) as exc:
        raise ValueError('DELIVERY_HTML_INVALID') from exc
    if not parser.closed or not ''.join(parser.parts).strip():
        raise ValueError('DELIVERY_HTML_BODY_REQUIRED')
    from io import BytesIO
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError('DELIVERY_PYPDF_REQUIRED_INSTALL_REQUIREMENTS') from exc
    try:
        if not payloads['pdf'].startswith(b'%PDF-'):
            raise ValueError('Not a PDF')
        pdf = PdfReader(BytesIO(payloads['pdf']), strict=True)
        if pdf.is_encrypted or not len(pdf.pages):
            raise ValueError('No readable pages')
        texts = [(page.extract_text() or '').strip() for page in pdf.pages]
        if not any(texts):
            raise ValueError('No report text')
        pages = len(pdf.pages)
    except Exception as exc:
        raise ValueError('DELIVERY_PDF_INVALID_OR_NO_TEXT') from exc
    return {
        'status': 'DELIVERY_FILES_READY',
        'html': str(paths['html']), 'pdf': str(paths['pdf']), 'pdf_pages': pages,
        'files': {kind: {'bytes': len(data), 'sha256': sha256(data).hexdigest()}
                  for kind, data in payloads.items()},
        'scope': 'FILE_READABILITY_ONLY',
        'content_and_visual_review': 'REQUIRES_CODEX_REVIEW',
        'live_call': False,
    }
