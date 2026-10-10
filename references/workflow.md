# 실행 인터페이스

아래 `python`은 설치한 가상환경의 Python을 뜻한다. Windows에서는 `.venv\Scripts\python`, Mac에서는 `.venv/bin/python`으로 대체하거나 가상환경을 활성화한다.

`python scripts/eziwork.py --workspace /출력/작업공간 <명령>` 형태다. 경로에 공백이 있으면 따옴표를 사용한다. Windows에서도 같은 Python 명령을 사용하며 실행파일이 `python3`인 Mac은 그 이름을 사용한다. 전체 수집은 기본 실행하지 않는다.

## 요청·수집
요청 JSON: `schema_version:1`, `report_type:P01..P14`, `target:{subject_id,property_name,lawd_cd,legal_dong,lot_number}`, `period:{start_ym,end_ym}`, `transaction_type`, `sources:[출처ID]`, `params:{출처ID:{공식조회조건}}`. 자료별 추가 식별자·날짜 필터는 `scripts/collection/registry.json`과 `references/collection-details.md`를 따른다. 해당되지 않는 필드는 생략한다. 대상이 불분명한 자료를 임의로 연결하지 않는다.

명령:
```
python scripts/eziwork.py preflight --request request.json
python scripts/eziwork.py collect --request request.json --run-id case-v01
python scripts/eziwork.py collect --request request.json --run-id case-v01 --resume
python scripts/eziwork.py collect --request request.json --run-id case-v02 --force-refresh
python scripts/eziwork.py privacy-check --file sanitized.json
python scripts/eziwork.py import --request request.json --run-id case-v01 --file sanitized.json --privacy-reviewed
python scripts/eziwork.py status --run-id case-v01
python scripts/eziwork.py prepare --run-id case-v01 --report P01 --review coverage-review.json
```
파일 접수는 `scripts/collection/prepare_input.py --source S15 --files sanitized.csv --output received --privacy-reviewed`와 해당 출처의 forms를 사용한다. 원본 복사 전에 개인정보 신호를 검사하며 개인정보 없는 자료만 접수한다. Excel은 필요한 항목만 CSV로 내보낸다. coverage-review는 실제 원문 대조한 항목에만 VERIFIED를 부여한다. `prepare`가 HOLD이면 필요한 근거 없이 actual report를 출력하지 않는다. 제공 범위를 줄일 때 요청한 핵심 질문을 충족하는지 다시 판단하고 유형의 필수 근거를 임의 삭제하지 않는다.

## 리포트 계약 v1
Codex가 작성하는 JSON은 다음 필드를 갖는다.
- `schema_version:1`, `report_id`, `mode:actual|historical_replay|synthetic_test`, `title`, `question`, `basis_date`, `scope`.
- `dataset`: 계약 파일 기준 상대 경로; `dataset_sha256`: prepare 출력 파일의 SHA256. 실제 모드는 READY_WITH_DECLARED_SCOPE 출력만 사용한다.
- `target`: actual 모드는 prepare 출력의 target 객체와 정확히 같아야 한다. report_id도 prepare 결과와 일치해야 한다.
- `sources`: `{id,title,url,basis_date}` 배열. 사용자 제공표는 `provided:summary` 등으로 원문 링크와 구분한다.
- `claims`: `{id,source_ids,record_index,field,value}`. record의 values에서 field를 읽는다. 계산 claim은 앞서 나온 claim의 `inputs`와 `operation:sum|difference|product|ratio|median`, 계산 결과 value를 가진다.
- 원자료의 provenance.units 또는 units를 우선 사용한다. 원·㎡ 필드 및 합·차·중앙값의 단위는 그래프와 자동 대조한다. 단위 메타데이터가 없는 사용자 표는 원자료의 단위를 확인하고 claim.unit에 적는다. 배율·백분율·만원 환산은 계산 근거와 결과 단위를 함께 기록하며 Codex가 차원을 검토한다.
- `blocks`: `{id,title,paragraphs:[문장],claim_ids:[ID],highlights:[원문 일부],figure_ids:[ID]}`.
- 제목·문단의 숫자는 `{{CLAIM_ID}}`, `{{CLAIM_ID:number}}`, `{{CLAIM_ID:krw}}`, `{{CLAIM_ID:percent}}`로 연결한다. 예: `호가는 {{PRICE:krw}}입니다.` 원자료가 문자열인 날짜·동 이름도 token으로 연결한다. 숫자를 직접 적으면 NUMERIC_TEXT_UNBOUND로 차단한다. token은 block의 claim_ids에 포함해야 한다. 원화 포맷은 원 단위 입력, percent는 퍼센트 단위 입력이다.
- `figures`: `{id,type:bar|dot|building|table,title,unit,points:[{label,claim_id,value}],note}`. 각 그림값은 claim과 같아야 한다. title·note·label 속 숫자도 claim token으로 연결한다. unit은 원·만원·㎡·% 같은 단위만 적는다. building은 설명용 층수 도식이다. 향·구간·욕실 등 복합 도식은 선택 예시의 SVG를 새 데이터로 설계하고 별도 수치 대조 기록을 남긴다.
- `qa:{evidence_review:PASS,copy_review:PASS}`는 실제 Codex 검토를 수행한 뒤에만 쓴다. 이 값은 독립적인 자동 사실 인증이 아니다.

```
python scripts/eziwork.py verify --contract report.json
python scripts/eziwork.py render --contract report.json --output 결과/v01 --branding config/branding.json --pdf
python scripts/eziwork.py pdf --input 검증된-맞춤.html --output 결과/v02.pdf
```
기존 출력이 있으면 새 버전을 사용한다. 숫자 수정 시 데이터→claim→문장→시각화 순서로 갱신하고 검토도 다시 수행한다. 렌더러는 외부 리소스를 차단하므로 폰트·그림은 로컬/내장으로 구성한다. 페이지형 .sheet 문서는 각 페이지를 검증해 병합하며, 연속형은 자연스러운 페이지 흐름을 사용한다.

## 2.2.0 추가 연결

지도·외부 그래프의 선택 필드와 실행 순서는 [통합 안내](integrations.md)를 따른다. 맞춤 HTML이 연속형이면 `<meta name="eziwork-page-flow" content="natural">`을 넣는다. V 표지는 각각 한 장으로 출력하고 본문은 자연스럽게 나눈다. 본문 꼬리말이 별도 빈 장으로 넘어가지 않도록 마지막 설명과 묶고, PDF에서 좌우 여백과 한글 잘림을 확인한다.
