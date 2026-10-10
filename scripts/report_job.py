"""Persist the current request and resume point; this is not an AI writer."""
from pathlib import Path
import json
from delivery import file_hash, check_receipt
from collector import write


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def start(request, job, mode):
    request, job = Path(request).resolve(), Path(job).resolve()
    data = load(request)
    if data.get('report_type') not in [f'P{i:02}' for i in range(1, 15)] or not isinstance(data.get('target'), dict) or not data.get('question'):
        raise ValueError('JOB_QUESTION_REPORT_TYPE_TARGET_REQUIRED')
    if mode not in ('actual', 'historical_replay', 'synthetic_test'):
        raise ValueError('JOB_MODE_INVALID')
    if job.exists():
        old = load(job)
        if old.get('request_sha256') != file_hash(request) or old.get('mode') != mode:
            raise ValueError('JOB_EXISTS_USE_NEW_VERSION')
        return status(job)
    write(job, {'schema_version': 1, 'request': str(request), 'request_sha256': file_hash(request),
                'mode': mode, 'stage': 'EVIDENCE_AND_DRAFT_REQUIRED'})
    return status(job)


def current(job):
    data = load(job)
    if data.get('schema_version') != 1:
        raise ValueError('JOB_FORMAT_UNSUPPORTED')
    if file_hash(data['request']) != data['request_sha256']:
        raise ValueError('JOB_REQUEST_CHANGED_USE_NEW_VERSION')
    return data


def bind(job, contract, verified_contract):
    data = current(job)
    request = load(data['request'])
    if (verified_contract.get('report_id') != request['report_type'] or
        verified_contract.get('question') != request['question'] or
        verified_contract.get('target', {}) != request['target'] or
        verified_contract.get('mode') != data['mode']):
        raise ValueError('JOB_CONTRACT_REQUEST_MISMATCH')
    data.update(contract=str(Path(contract).resolve()), contract_sha256=file_hash(contract), stage='OUTPUT_REQUIRED')
    data.pop('delivery', None)
    write(Path(job), data)
    return status(job)


def status(job):
    data = current(job)
    result = {'job': str(Path(job).resolve()), 'status': data['stage'], 'complete': False}
    if 'contract' not in data:
        return {**result, 'next_action': 'Collect/review required evidence, author the contract, then report-job bind.'}
    if not Path(data['contract']).is_file() or file_hash(data['contract']) != data['contract_sha256']:
        return {**result, 'status': 'CONTRACT_REVIEW_REQUIRED', 'next_action': 'Verify and bind the revised contract; regenerate outputs.'}
    if data['stage'] == 'COMPLETED':
        try:
            checked = check_receipt(data['delivery']['html'], data['delivery']['pdf'], data['contract'])
        except (OSError, ValueError, KeyError):
            return {**result, 'status': 'OUTPUT_REBUILD_REQUIRED', 'next_action': 'Regenerate and review the current HTML/PDF, then finish again.'}
        checked['content_and_visual_review']=data.get('review','CODEX_ATTESTED_NOT_AUTOMATICALLY_PROVEN')
        return {**result, 'complete': True, 'delivery': checked, 'next_action': 'Deliver both file links to the user.'}
    return {**result, 'next_action': 'Render HTML/PDF with the bound contract, review both, then report-job finish.'}


def finish(job, html, pdf, reviewed=False):
    if not reviewed:
        raise ValueError('CONTENT_AND_VISUAL_REVIEW_REQUIRED')
    data = current(job)
    if not data.get('contract') or file_hash(data['contract']) != data.get('contract_sha256'):
        raise ValueError('BIND_CURRENT_CONTRACT_FIRST')
    checked = check_receipt(html, pdf, data['contract'])
    data.update(stage='COMPLETED', delivery=checked, review='CODEX_ATTESTED_NOT_AUTOMATICALLY_PROVEN')
    write(Path(job), data)
    return status(job)
