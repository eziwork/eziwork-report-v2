# 공식 공개자료 접수 · 2.3.0

주소 S07은 기존 VWorld CLI의 geocode/역지오코딩을 사용한다. 도로명/지번과 좌표를 함께 저장하고 시도·시군구·법정동을 대조한다. 이 좌표는 주소 조회점이며 특정 동·호실이나 필지 경계를 증명하지 않는다.

S12 학교와 S17 법령은 API를 호출하지 않는다. 연결된 브라우저에서 공식 원문을 열어 다운로드하거나 공개 파일을 받는다. 브라우저가 없으면 BROWSER_REQUIRED, 접근이 막히면 ACCESS_RESTRICTED, 지원하지 않는 형식은 UNSUPPORTED_FORMAT 상태로 남기고 공식 PDF·CSV·JSON·GeoJSON 또는 확인한 텍스트 사본을 요청한다. 실패를 0건으로 기록하지 않는다.

## 원문 확보와 추출

학교 위치: [전국초중등학교위치표준데이터](https://www.data.go.kr/data/15021148/standard.do). 학교 코드·학교급·운영상태·주소·좌표·자료 기준일을 선택한 학교의 원문 행과 대조한다.
학구: [학구도안내서비스](https://schoolzone.emac.kr/). 공공데이터포털의 학구 목록만으로는 경계 도형이 확보된 것이 아니다. 공식 도형과 학교 코드 연결표가 모두 필요하다.
배정: 관할 교육지원청 해당 학년도의 **확정 공고**와 공동통학·예외 조건을 대조한다. 행정예고는 확정 공고로 취급하지 않는다.
법령: [국가법령정보센터](https://www.law.go.kr/), [토지이음](https://www.eum.go.kr/) 및 대상 지자체의 조례·고시. 검색 목록만 받으면 조문 검증 완료가 아니다. 본문·시행일·부칙·별표와 필요한 관할·용도를 확인한다.

```text
python scripts/eziwork.py official-document --file official.pdf --url https://www.law.go.kr/... --output extracted-v01
```

원본 파일의 SHA256과 추출 파일의 SHA256을 기록한다. 추출 성공은 검토 완료가 아니다. HTML/PDF/CSV/JSON/TXT/GeoJSON만 지원한다. HWP·SHP만 확보한 경우 공식 PDF·GeoJSON 등을 추가로 받거나 변환본을 원문과 대조해 기록한다. 추출 오류가 난 원문을 빈 값으로 대체하지 않는다.

## 접수 양식

`scripts/collection/forms/S07.json`, `S12.json`, `S17.json`을 사용한다. `data_format_version:2`, `intake_channel:OFFICIAL_PUBLIC`, `review_status:VERIFIED`는 실제 대조 후 기록한다. 각 attachment는 원본 file·source_url·sha256을 갖는다.

각 행의 `original_proof`에는 원본 해시, 검토 상태, `field_quotes`를 기록한다. 원문의 문구를 직접 발췌하고 정규화 값과 대조한다. 법령 시행일은 원문의 “2026. 5. 17.” 같은 표현을 ISO 날짜로 변환해 대조할 수 있다. 법령의 addenda_review/annex_review는 REVIEWED 또는 실제 원문에 없을 때 NONE_IN_SOURCE로 구분한다.

공식 자료의 공개 기관 연락처가 개인정보 탐지에 걸리면 `public_contact_review`에 원문 해시·정확한 연락처·institutional_public_contact:true·검토 이유를 적는다. 해당 원문에 존재하는 기관 연락처만 예외 처리한다. 주민번호는 예외 대상이 아니다. 고객 첨부자료에는 이 경로를 사용하지 않고 기존 개인정보 검사를 유지한다. 자동 탐지는 완전하지 않다.

```text
python scripts/eziwork.py import --request request.json --run-id case-v01 --file official-input.json --privacy-reviewed
```

## 학구 경계

Shapely 2.1.2·pyproj 3.7.2를 사용한다. GeoJSON FeatureCollection의 각 feature.properties.zone_id와 학교 연결표 JSON `{"구역코드":["학교코드", "..."]}`가 필요하다. 원본이 SHP이면 좌표계를 보존한 GeoJSON 변환본과 원본의 관계를 검토하고 기록한다.

catchment spec:
- geometry_file/geometry_sha256, join_file/join_sha256: spec 기준 상대 경로와 실제 SHA256
- source_crs: 원문 좌표계(예 EPSG:5179), source_url, basis_date
- target_id, lon, lat: 확인한 대상 주소의 WGS84 좌표

```text
python scripts/eziwork.py catchment --spec catchment.json --output catchment-result.json
```

UNIQUE_INTERIOR / BOUNDARY / MULTIPLE / NO_MATCH를 구분한다. 5cm 경계 허용오차를 기록하며, 근소한 좌표 차이를 배정 확정 근거로 사용하지 않는다. 복수 구역·공동통학 학교를 임의로 하나로 줄이지 않는다.

assignment 행은 학년도·FINAL 상태·공식 공고 URL/해시·예외 조건과 catchment_spec을 요구한다. import가 도형 계산을 다시 수행하며 request.target.lon/lat와 같아야 한다. 학구 도형·연결표·공고도 attachments에 포함해 원문을 보존한다. location 행은 배정 근거로 사용하지 않는다.

## 과거 기록

변경 전 S07·S12·S17 정의는 `legacy/collection-registry-2.2.0.json`에 보존했다. 과거 API 파서는 읽기 호환용이며 새 API 호출은 차단한다. 새 route_id는 vworld-address-v1 / official-school-v1 / official-law-v1이다. 과거 제공기관·조회일을 새 경로의 값으로 덮어쓰지 않는다.

수집 자료와 검토에는 data_format_version·validation_rule_version·route_id·provider·collection_channel·raw_sha256을 기록한다. 과거 VERIFIED만으로 통과시키지 않는다. 규칙이 바뀌었거나 원문/첨부 해시가 다르면 재검토하며, 출처 ID를 알 수 없으면 SOURCE_MIGRATION_REQUIRED로 안내한다.


학교 위치 조회에는 params.S12.school_code와 region을 명시합니다. 배정 판정에는 도형과 학교 연결표의 원본도 attachments에 포함합니다. 가까운 학교 위치와 배정 학교는 별개입니다.
