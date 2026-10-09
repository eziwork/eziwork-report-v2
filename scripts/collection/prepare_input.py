"""Copy source files, extract text/CSV, and produce a PENDING input envelope.

Never interpret extracted PDF text as verified structured contract/rights data.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
from collector import registry,write,CollectionError

def prepare(source_id, files, output, privacy_reviewed=False):
    if not privacy_reviewed:raise CollectionError('PRIVACY_REVIEW_REQUIRED')
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from eziwork import privacy_issues
    for file in files:
        if privacy_issues(file):raise CollectionError('PERSONAL_DATA_OR_UNREVIEWED_FORMAT')
    sources,_=registry();source=sources[source_id]
    if source['mode'] not in {'FILE','MANUAL','API'}: raise CollectionError('FILE_INPUT_ROUTE_REQUIRED')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    envelope=json.loads((Path(__file__).parent/'forms'/f'{source_id}.json').read_text(encoding='utf-8'))
    envelope['evidence_mode']='ACTUAL';envelope['attachments']=[]
    structured=[]
    for file in files:
        path=Path(file)
        if path.stat().st_size>30_000_000: raise CollectionError('INPUT_FILE_TOO_LARGE')
        suffix=path.suffix.lower()
        if suffix not in {'.pdf','.csv','.txt','.json'}: raise CollectionError('INPUT_FORMAT_UNSUPPORTED')
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest();dest=output/(sha+suffix)
        shutil.copyfile(path,dest)
        status='EXTRACTED';text=''
        if suffix=='.pdf':
            from pypdf import PdfReader
            reader=PdfReader(str(dest))
            if len(reader.pages)>300: raise CollectionError('INPUT_PAGE_LIMIT')
            text='\n'.join(page.extract_text() or '' for page in reader.pages)
            if not text.strip(): status='OCR_OR_MANUAL_REVIEW_REQUIRED'
        else:
            try: text=raw.decode('utf-8-sig')
            except UnicodeDecodeError: text=raw.decode('cp949')
            if suffix=='.csv': structured.extend(csv.DictReader(io.StringIO(text)))
            if suffix=='.json':
                data=json.loads(text)
                if isinstance(data,list) and all(isinstance(r,dict) for r in data): structured.extend(data)
        extracted=output/(sha+'.extracted.txt');extracted.write_text(text,encoding='utf-8')
        envelope['attachments'].append(dict(file=dest.name,sha256=sha,extracted_file=extracted.name,status=status))
    if structured: envelope['records']=structured
    envelope['source_url']='local-files:'+','.join(a['file'] for a in envelope['attachments'])
    write(output/'input.json',envelope)
    return output/'input.json'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--files',nargs='+',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--privacy-reviewed',action='store_true');a=p.parse_args()
    try: print(prepare(a.source,a.files,a.output,a.privacy_reviewed).resolve())
    except Exception as exc:
        print(json.dumps({'status':exc.code if isinstance(exc,CollectionError) else 'INPUT_EXTRACTION_FAILED'}));raise SystemExit(2)
