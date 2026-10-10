> 2.3.0 우선 적용: 새 API 허용 키는 5개이며 S07은 VWorld, S12·S17은 공식 파일입니다. 아래 과거 감사 기록의 주소·학교알리미·법령 API 상태는 새 실행 경로가 아닙니다. [현재 안내](api-setup.md) · [공식 접수](public-evidence.md)

# 수집 데이터 규칙

## 40개 경로와 자료 입력

`scripts/collection/registry.json`은 실거래 10종, 기타 공식 API 15종, 공개 사이트·서류 6종, 네이버 1종, 사용자 입력 8종을 연결합니다. `scripts/collection/forms`에는 40개 경로의 입력/대체 파일 양식과 보고서 검토 양식이 있습니다. 아래 명령은 스킬 폴더 기준입니다.

- API: `preflight` 후 `collect`. Vworld S04/S05는 공식 명세의 정확한 레이어 ID와 `layer_guide_url`을 지정해야 합니다. 지적도 `jiga`를 공시지가 경로로 대체하지 않습니다.
- API 파일 대체: 키·승인 대기 시 공식 CSV/JSON을 `prepare_input.py`로 접수하고 같은 출처 ID로 `import`할 수 있습니다. 공식 원본 첨부, 원문 필드명·단위 유지, `api_file_mode: true`, `native_units_confirmed: true`, VERIFIED 검토가 필요합니다. 실거래 금액 필드는 만원 단위입니다. 한국어 CSV 헤더를 API 필드로 매핑했다면 원본과 매핑을 함께 보관하세요. 동일 정규화 검증을 적용하며 실제 API 연결 성공으로 승격하지 않습니다.
- 주소 S07: 주소 검색 어댑터입니다. 좌표 API는 별도 승인과 명세 검증 전 미지원입니다.
- 법령 S17: 새 실행은 공식 원문 파일과 조문·시행일·부칙·별표 검토를 사용합니다. 과거 API 검색 결과는 보존하되 현행 검증 없이 재사용하지 않습니다. public-evidence.md를 따릅니다.
- 네이버: [연결 브라우저 절차](naver-collection.md)를 따릅니다. 최대 20광고를 검증한 후 입력합니다. CLI 단독으로 브라우저를 조작하지 않습니다.
- 파일: 개인정보 없는 자료를 직접 검토하고 `python scripts/collection/prepare_input.py --source S15 --files sanitized.pdf --output received/S15 --privacy-reviewed`로 접수합니다. 탐지 신호가 있거나 이미지 PDF라면 복사를 시작하지 않고 정리된 자료를 요청합니다. CSV/JSON 배열은 구조화 행을 읽고, PDF 텍스트는 자동으로 권리판단 필드로 변환하지 않습니다.
- 수동: 해당 양식의 필수값과 기준일/발급일, 대상 식별정보를 채우고 원본과 대조한 뒤 VERIFIED로 변경합니다. EXAMPLE 자료는 테스트용이며 보고서에 사용되지 않습니다.

첨부파일과 화면 증거는 입력 JSON 기준의 상대 경로로 지정합니다. `import`는 파일 존재·크기·해시를 검사하고 실행 폴더에 원본을 보관합니다. 사용자 입력을 위해 새 실행을 만들 때 API 수집을 자동으로 실행하지 않습니다.

## 결과와 보고서 연결

`runs/<실행 ID>/`에 `request.json`, `manifest.json`, `raw`, `normalized`, `checkpoints`, `status.html`이 생성됩니다. 연결 오류는 반환 건수 `null`, 정상 조회 0건은 `0`입니다. 지역 전체 반환 건수와 대상에 사용할 수 있는 건수는 다릅니다. 자료가 미완료면 저장된 행도 분석에서 제외합니다. 같은 값의 실거래를 동일 거래라고 임의 삭제하지 않습니다.

14개 보고서·58개 자료 요구사항은 `manifest.json.readiness`에 연결됩니다. 무조건 필수 그룹은 누락 시 HOLD, 조건부 필수 그룹은 요청의 `required_groups`에 그룹명을 넣어 활성화합니다. 나머지 누락 그룹은 EXCLUDED로 표시합니다. 출처 목록은 제공원 목록이며 모두가 서로의 대체 자료라는 뜻은 아닙니다. 수집된 자료는 우선 COLLECTED_PENDING_COVERAGE_REVIEW로 남깁니다.

`forms/report-coverage-review.json`의 실행 ID와 해당 요구사항들을 채웁니다. 각 체크 항목에 확인한 `source_id`, 정규화 배열의 `record_index`(0부터), 실제 확인한 `fields`, 검토 메모를 지정하고 VERIFIED로 변경합니다. 필드 존재와 사용 가능 행을 검사한 후 행 해시에 검토를 묶습니다. 예를 들어 지적도 면적만으로 등기 권리 항목을 확인 처리하면 안 됩니다. 필드 내용이 항목을 충족하는지는 원문 대조 검토가 필요합니다. 재수집·추가 입력 또는 검토한 행 변경 시 다시 검토해야 합니다.

공식 참고자료의 API 성공은 특정 대상의 증명이 아닙니다. 실거래는 지역 코드와 PNU, 법정동·지번 또는 실거래 단지 식별번호(`complex_id`)로 대조합니다. 건축물은 `target.pnu`, 공동주택은 `target.kapt_code`와 지역·필지로 연결합니다. `display_name`은 표시용 이름이며 `property_name`을 지정하면 기관 원문 이름도 정확히 일치해야 합니다. 이름만 같거나 임의의 `reference_bindings`만 일치하는 자료는 통과하지 않습니다. 기관별 원문 필드는 `raw_fields`에 보존하며, 보고서 내보내기 시 현재 요청과 다시 대조합니다.

기관 갱신일을 제공하지 않는 건축물·단지 기본정보는 `basis_date: null`, `basis_type: OBSERVED_SNAPSHOT`과 실제 관측 시각으로 보관합니다. 기관 기준일을 만들어 넣지 않습니다. 지역 자료는 `source_scopes.S10: DISTRICT_CONTEXT`, LH 전국 자료는 `source_scopes.S20: NATIONAL_CONTEXT`처럼 분석 범위를 명시하며, 개별 부동산 증거와 구분합니다. LH `REGION` 범위는 반환된 시도와 대상 지역을 비교합니다. 다른 출처의 미지원 범위는 확인 대기로 제외합니다.

LH 게시 기간과 마감 기간은 별도 조건입니다. `date_filters.S20`에 `published_from`, `published_to`(필수), `closing_from`, `closing_to`(선택 쌍)를 ISO 날짜로 지정합니다. 공식 요청 변수 `PAN_ST_DT/PAN_ED_DT`, `CLSG_ST_DT/CLSG_ED_DT`로 변환하며, `dsSch`의 실제 적용 조건과 각 행의 게시일·마감일을 모두 검사합니다. 응답 필드 `PAN_NT_ST_DT/CLSG_DT`를 요청 조건으로 사용하면 오류로 중단합니다. 직접 `params.S20`에 지정할 때는 공식 변수와 YYYYMMDD 형식을 사용합니다.

```powershell
python scripts/eziwork.py --workspace output prepare --run-id my-report --report P01
python scripts/eziwork.py --workspace output prepare --run-id my-report --report P01 --review my-coverage-review.json
```

필수 자료 부족 시 빈 records의 HOLD 결과를 만듭니다. 준비가 된 경우에만 사용 가능한 행과 제외 항목을 내보냅니다. v2 보고서 생성기는 이 파일을 입력으로 사용해야 합니다. `verify`와 `render`는 HOLD 자료의 실제 보고서 출력을 차단합니다.

