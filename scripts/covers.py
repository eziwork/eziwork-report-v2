"""V bookends. Decorative architecture is never property evidence."""
from pathlib import Path
import base64
import html
import json
import re

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('title', 'subtitle', 'closing_title', 'closing_text')

def wrap_document(document, metadata, brand=None, image_url=None):
    """Add exactly two bookends to reviewed HTML; leave the body unchanged.

    Caller supplies reviewed metadata. Contract rendering binds all numeric
    cover copy to claims before this function. image_url is for bundled examples.
    """
    if 'data-ezi-cover="V"' in document:
        raise ValueError('COVERS_ALREADY_PRESENT')
    if not re.search(r'</head\s*>', document, re.I) or not re.search(r'<body\b[^>]*>', document, re.I) or not re.search(r'</body\s*>', document, re.I):
        raise ValueError('COMPLETE_HTML_REQUIRED')
    if metadata.get('mode') not in ('actual', 'historical_replay', 'synthetic_test'):
        raise ValueError('COVER_MODE_REQUIRED')
    if not metadata.get('basis_date') or not metadata.get('title'):
        raise ValueError('COVER_TITLE_DATE_REQUIRED')
    types = json.loads((ROOT/'references/report-types.json').read_text(encoding='utf-8-sig'))['reports']
    kind = next((r['report_type'] for r in types if r['report_id'] == metadata['report_id']), None)
    if not kind:
        raise ValueError('COVER_REPORT_TYPE')
    brand = brand or {}
    esc = lambda v: html.escape(str(v), quote=True)
    lines = lambda v: '<br>'.join(esc(v).split('\n'))
    if image_url is None:
        image_url = 'data:image/png;base64,' + base64.b64encode((ROOT/'assets/cover-v.png').read_bytes()).decode('ascii')
    company = brand.get('business_name') or 'EZIWORK'
    contact = ' · '.join(str(brand[k]) for k in ('contact_name', 'phone') if brand.get(k))
    mode = {'actual':'', 'historical_replay':'과거 자료 재생 사례 · 현재 매물 안내가 아닙니다.', 'synthetic_test':'합성 검증 예시 · 실제 시세가 아닙니다.'}[metadata['mode']]
    title = metadata['title']
    # Keep short target names large; long questions get their own smaller scale.
    longest = max(len(s) for s in title.split('\n'))
    size = 9.07 if longest <= 11 else 7 if longest <= 22 else 5.7 if longest <= 40 else 4.8
    header = f'<div class="ec-brand">{esc(company)}<span>부동산 상담</span></div>'
    footer = f'<div class="ec-footer"><span>{esc(kind)}</span><span>기준일 {esc(metadata["basis_date"])}</span></div>'
    photo = f'<img class="ec-photo" src="{esc(image_url)}" alt="" aria-hidden="true">'
    front = f'''<div class="ezi-cover" data-ezi-cover="V" data-cover-side="front"><div class="ec-canvas">
{photo}{header}<div class="ec-kind">{esc(kind)}</div>
<div class="ec-title" style="font-size:{size}cqw">{lines(title)}</div>
<div class="ec-question">{lines(metadata.get('subtitle', '대상과 주요 조건을\n함께 살펴보세요.'))}</div>
<div class="ec-diagonal"></div><div class="ec-meta">자료 기준일<br><strong>{esc(metadata['basis_date'])}</strong>{('<small>'+esc(mode)+'</small>') if mode else ''}</div>{footer}</div></div>'''
    back = f'''<div class="ezi-cover ec-back" data-ezi-cover="V" data-cover-side="back"><div class="ec-canvas">
{photo}{header}<div class="ec-closing">{lines(metadata.get('closing_title', '궁금한 내용과\n조건을 말씀해 주세요.'))}</div>
<div class="ec-body">{lines(metadata.get('closing_text', '관심 있는 대상과 궁금한 내용을 알려주시면\n다음 상담에서 함께 살펴보겠습니다.'))}</div>
<div class="ec-contact"><div class="ec-label">상담 안내</div><strong>{esc(company)}</strong>{('<span>'+esc(contact)+'</span>') if contact else ''}</div>{footer}</div></div>'''
    css = (ROOT/'assets/cover-v.css').read_text(encoding='utf-8')
    document = re.sub(r'</head\s*>', lambda m: '<style data-ezi-cover-style="V">'+css+'</style>'+m[0], document, count=1, flags=re.I)
    document = re.sub(r'<body\b[^>]*>', lambda m: m[0]+front, document, count=1, flags=re.I)
    return re.sub(r'</body\s*>', lambda m: back+m[0], document, count=1, flags=re.I)
