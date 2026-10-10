# 세 스킬 번들 — 2.2.0

`eziwork-report-v2`가 단일 진입점이다. 원본은 `vendor/`, EZIWORK 조정은 이 문서와 `humanizer-profile.md`, `scripts/integrations.py`, `scripts/scientific_charts.py`에 분리한다. 원본을 수정하지 않는다. `integrations-lock.json`의 커밋·해시를 확인하며 자동 업데이트를 호출하지 않는다.

## 실행 순서

요청·근거 준비 → 필요한 지도·그래프 → 원고·캡션 → 한국어 교정 → 사실·수치 재대조 → HTML·PDF 검수. 각 단계의 산출물과 해시를 해당 실행 폴더에 보존한다. 키와 고객 원본을 번들에 넣지 않는다.

```
python scripts/eziwork.py integrations check
python scripts/eziwork.py integrations setup
python scripts/eziwork.py integrations setup --python
python scripts/eziwork.py map --request map-request.json --output run/maps-v01
python scripts/eziwork.py chart --spec chart-spec.json --output run/chart-v01
```

`check`와 `doctor`는 로컬 검사이며 API를 호출하지 않는다. `setup`은 현재 OS용 VWorld 0.3.5 공식 실행파일만 다운로드하고 고정 SHA-256을 검증한다. Python 패키지는 `requirements.txt`로 설치한다. `EZIWORK_RUNTIME_DIR`과 `EZIWORK_KOREAN_FONT`로 실행파일 위치와 한글 글꼴을 지정할 수 있다. 무도메인 키에 임의 referer를 붙이지 않는다. 등록 도메인이 있으면 `VWORLD_DOMAIN`에 그 값을 설정한다.

## 지도

`setup --python`을 쓰면 고정 Python 패키지도 스킬의 runtime/python에 설치한다. 시스템 Python 패키지와 분리되며 설치 점검은 API를 호출하지 않는다.

먼저 `vendor/vworld/SKILL.md`, `LEARNINGS.md`, 필요한 명령의 `references/docs/USAGE.md`를 읽는다. 키는 기존 `configure --name VWORLD_API_KEY`의 숨김 입력과 환경 설정 우선순위를 따른다. 원본의 `config add-key` 예시처럼 키를 명령 인수로 넣지 않는다. 어댑터는 잠깐 생성한 별도 설정을 원본 CLI에 전달하고 정리한다.

요청 예시:
```json
{"targets":[{"label":"잠실엘스","address":"서울특별시 송파구 올림픽로 99","type":"ROAD","expected_tokens":["서울특별시","송파구","올림픽로","99","잠실엘스"]}],"zoom":16}
```

`expected_tokens`는 조회 전에 근거 주소의 시군구·도로/법정동·건물번호/지번과 알려진 건물명을 모두 포함한다. 빈 값·번호 일부·중복 후보는 채택하지 않는다. 자동 문자열 대조 후 반환 주소와 대상 동일성을 Codex가 다시 확인한다. 정확한 번지가 없으면 임의 중심점을 표시하지 않는다. 지도 필요성이 없는 임대운영 보고서에는 억지로 지도를 넣지 않는다.

주소 조회점, 건물, 필지 경계를 구분한다. 표시점은 동호실·출입구·단지 중심이 아니다. 원본 배경의 출처 로고를 보존하고 이름표·조회일·주소를 별도 캡션에 넣는다. 원본 PNG와 geocode 응답을 보존한다. `map-provenance.json`의 HOLD는 성공 지도로 대체하지 않는다. 실거래 자료 기준일과 지도 조회일은 각각 표시한다. 토지이용·공시지가·지적도는 별도 수집 경로이며 이 지도 성공으로 검증 완료 처리하지 않는다.

작업 뒤 새로 확인한 내용만 실행 폴더의 `vworld-learnings.md`에 `날짜 | 명령/대상 | 결과 | 원인 | 다음 적용`으로 기록한다. 고정 원본 LEARNINGS.md를 변경하지 않는다.

## 한국어

`vendor/korean-humanizer/SKILL.md`와 `references/ko-ai-signals.md` 전체, [EZIWORK 프로필](humanizer-profile.md)을 실제 읽고 제목·본문·결론·표·지도·그래프 캡션을 교정한다. 별도 AI API나 가짜 humanizer CLI를 호출하지 않는다. Codex가 원본 지침을 적용한 기록을 `copy-review.json`으로 남긴다. 기술 로그의 실행 여부와 의미 검토의 자기기록을 구분한다.

## 그래프

`vendor/scientific-visualization/SKILL.md`와 `references/publication_guidelines.md`를 읽는다. 고객 보고서용으로 적용하며 학술지 인증·투고 기준은 적용하지 않는다. 코드로 만든 숫자와 텍스트를 쓰고 이미지 생성 모델에 그래프 수치를 맡기지 않는다.

`chart-spec.json`은 원자료 `dataset`, `dataset_sha256`, `title`, `unit`, `basis_date`, `scope`, `kind`(bar/dot/line), `points`를 가진다. 각 점은 `label`, JSON Pointer인 `pointer`를 가진다. `display_divisor`(예: 원→억원은100000000)와 `display_unit`은 표시 환산에만 쓴다. 결측은 null로 유지하고 월별 자료는 누락 월을 먼저 명시한다. 원자료의 해제·대상·면적·기간 검토를 통과한 행만 포인터로 연결한다. 합성 시험은 실제 자료와 별도 폴더로 둔다.

원본 `figure_export.export_figure`, `palette_audit.py`, `image_metadata.py`를 실제 실행한다. SVG·PNG·자료표 CSV·provenance를 함께 만든다. 단일 색 그래프에도 항목·직접 수치를 표기한다. 복합 분포도는 동일 원본 exporter와 검사 도구를 쓰는 별도 스크립트로 제작하고 전체 관측값·계산 방법을 보존한다. 자동 검사 통과는 문장 의미·접근성·고객 활용성을 완전히 증명하지 않는다.

## v1 계약의 추가 필드

기존 계약은 변경 없이 실행된다. 선택 필드 `assets`와 블록의 `asset_ids`를 추가한다. asset은 `id,kind,file,sha256,provenance,provenance_sha256,alt,caption`을 갖는다. chart에는 `unit,points[{label,claim_id}]`, map에는 `address_review:PASS`를 추가한다. 그래프 provenance의 points·단위·출력 해시는 같은 claim 값과 일치해야 한다. 지도는 주소·배경 검토 완료와 원본 해시가 필요하다. 외부 그림은 출력 HTML에 포함하며 그래프 자료표도 제공한다.

기존 조회 그림을 재사용하면 provenance 조회일과 입력 해시를 유지한다. 수정된 입력은 새 그림 폴더로 출력한다. 출력 도중 실패한 폴더는 미완료로 두고 새 버전에서 재실행한다.

EZIWORK 그래프 스타일은 ssets/scientific-style.json에 별도로 둡니다. 원본 exporter와 스타일 파일은 수정하지 않습니다.
