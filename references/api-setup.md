# API 설정과 복구

선택 보고서에 필요한 출처만 설정한다. 키 값은 채팅에 붙이지 않는다. `python scripts/eziwork.py configure --name DATA_GO_KR_SERVICE_KEY`는 숨김 입력으로 로컬 설정에 저장하며 호출하지 않는다.

우선순위: 프로세스 환경변수 → `EZIWORK_CREDENTIAL_FILE` 지정 파일 또는 config/local-credentials.json → config/default-credentials.json. `EZIWORK_DISABLE_BUNDLED_KEYS=1`이면 기본 키를 쓰지 않는다. 설정 파일은 허용된 8개 부동산 데이터 키만 읽는다. 공개본에는 실제 인증키를 포함하지 않는다. 공식 안내에 따라 발급받은 개인 키를 환경변수 또는 로컬 설정에 등록한다. 기본 설정 파일은 비어 있으며 파일 입력과 합성 예시는 키 없이 사용할 수 있다.

공공데이터포털은 로그인 → 정확한 서비스의 활용신청 → 승인 확인 → 키 등록 → 해당 출처 preflight/표본 수집 순서다. 같은 키라도 서비스별 활용승인은 별개다. 다른 기관도 아래 공식 안내에서 계정·이용신청·발급·도메인 제한을 확인한다. 이용자 동의와 CAPTCHA는 대신 우회하지 않는다.

| 상태 | 처리 |
|---|---|
| KEY_MISSING | 해당 서비스 발급 후 로컬 설정 |
| AUTH_REJECTED | 활용승인·설정·키 형식·폐기/만료 확인. 원인 확인 전 만료로 단정하거나 반복 호출하지 않음 |
| AUTH_APPROVAL_REQUIRED | 제공기관이 이용 권한 거절을 명시한 경우 해당 API 활용신청·승인 상태 확인 |
| KEY_NOT_REGISTERED | 제공기관이 미등록 키라고 응답. 키 설정과 서비스 신청 상태 확인; 만료로 단정하지 않음 |
| CREDENTIAL_EXPIRED_CONFIRMED | 공공데이터포털이 만료 코드 31 또는 명시적 만료 메시지를 반환한 경우 이용 기간·갱신 확인 |
| REQUEST_CONFIG_INVALID/ENDPOINT_UNAVAILABLE | 조회 변수·서비스 주소와 공식 명세 확인 |
| PARAMS_REQUIRED | 공식 코드·날짜·필지·레이어 등 필요한 조회조건 안내 |
| RATE_LIMITED | 응답 재개 조건에 따른 제한된 재시도, 실패 시 새 실행 대신 재개 |
| TIMEOUT/SERVER_UNAVAILABLE | 최대 3회 시도 후 상태 보존 |
| RESPONSE_INVALID/페이지 불일치 | 미완료로 보존, 분석 사용 제외 |
| 정상 0건 | 정상 조회 기간·범위를 명시하고 오류와 구분 |

입력 파일 대체는 같은 출처의 검토된 공식 원본을 쓰되 API 연결 성공으로 표시하지 않는다. 만료가 확인된 경우에만 재발급·갱신 안내를 제공한다. 전체 서비스 운영 상태는 각 사용자 계정으로 다시 확인해야 한다.

## 기관별 설정 확인

- **DATA_GO_KR_SERVICE_KEY**: 공공데이터포털 마이페이지에서 사용할 서비스 각각의 승인 상태를 확인한다. 일반 키 값은 한 번만 저장하며 URL 인코딩을 임의로 두 번 적용하지 않는다. T01은 아래 상세 서비스의 개발계정과 상세 조회 엔드포인트를 대조한다.
- **VWORLD_API_KEY**: Vworld 개발자 화면에서 발급받은 키와 등록 도메인 조건을 확인한다. S04·S05는 공식 레이어 ID와 layer_guide_url도 필요하다. 키만 넣고 다른 레이어를 해당 자료라고 판단하지 않는다.
- **JUSO_CONFM_KEY**: 주소기반산업지원서비스에서 주소 검색용 승인키를 발급받는다. 현재 어댑터는 주소 검색이며 좌표 API 승인과 혼동하지 않는다.
- **KOSIS_API_KEY**: KOSIS OpenAPI 신청 후 기관·통계표·항목·주기·기간 코드를 공식 통계표와 맞춘다. 표본 응답의 단위와 지역 범위를 확인한다.
- **RONE_API_KEY**: 한국부동산원 R-ONE OpenAPI에서 키와 호출할 통계표·분류·기간 코드를 확인한다. 지역 통계를 개별 매물의 근거로 승격하지 않는다.
- **SCHOOLINFO_API_KEY**: 학교알리미 OpenAPI의 신청 및 제공 항목 안내에 따라 키를 발급받고 학교 코드·공시 항목·기준연도를 대조한다.
- **LAW_OC**: 국가법령정보 공동활용 신청 계정의 OC 식별값을 설정한다. 검색 목록 수신과 특정 법령 본문·시행일 검증은 별개다.
- **ECOS_API_KEY**: 한국은행 ECOS 인증키와 통계코드·주기·시작/종료시점·항목코드를 확인한다. 경제지표의 단위를 원화 거래금액으로 해석하지 않는다.

키 변경 후 같은 request.json으로 preflight를 실행하고, 필요한 출처 하나만 지정한 collect로 확인한다. 서비스가 명시한 승인 부족·폐기·만료 코드 또는 공식 계정 화면이 있을 때만 원인을 확정한다. AUTH_REJECTED만 반환하면 원인은 확인 대기이며 승인·키 형식·허용 도메인을 차례로 대조한다.

| ID | 자료 | 방식 | 설정 이름 | 안내 |
|---|---|---|---|---|
| T01 | 국토교통부_아파트 매매 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126468/openapi.do) |
| T02 | 국토교통부_연립다세대 매매 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126467/openapi.do) |
| T03 | 국토교통부_오피스텔 매매 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126464/openapi.do) |
| T04 | 국토교통부_단독/다가구 매매 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126465/openapi.do) |
| T05 | 국토교통부_상업업무용 부동산 매매 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126463/openapi.do) |
| T06 | 국토교통부_토지 매매 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126466/openapi.do) |
| T07 | 국토교통부_아파트 전월세 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126474/openapi.do) |
| T08 | 국토교통부_연립다세대 전월세 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126473/openapi.do) |
| T09 | 국토교통부_오피스텔 전월세 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126475/openapi.do) |
| T10 | 국토교통부_단독/다가구 전월세 실거래가 자료 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15126472/openapi.do) |
| S01 | 건축HUB 건축물대장정보 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15134735/openapi.do) |
| S02 | 공동주택 기본 정보제공 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15058453/openapi.do) |
| S03 | K-apt 월별 관리비 공개 | FILE | 불필요 | [공식 안내](https://www.k-apt.go.kr/) |
| S04 | 토지이용계획정보(WMS/WFS/속성정보) | API | VWORLD_API_KEY | [공식 안내](https://www.data.go.kr/data/15123973/openapi.do) |
| S05 | 개별공시지가정보(WMS/WFS/속성정보) | API | VWORLD_API_KEY | [공식 안내](https://www.data.go.kr/data/15124014/openapi.do) |
| S06 | 연속지적도형정보(WMS/WFS) | API | VWORLD_API_KEY | [공식 안내](https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=cadastral) |
| S07 | 주소 검색·좌표 API | API | JUSO_CONFM_KEY | [공식 안내](https://business.juso.go.kr/) |
| S08 | KOSIS 통계자료·공유서비스 | API | KOSIS_API_KEY | [공식 안내](https://kosis.kr/openapi/devGuide/devGuide_0201List.do) |
| S09 | 부동산통계(R-ONE) 조회 | API | RONE_API_KEY | [공식 안내](https://www.reb.or.kr/r-one/portal/openapi/openApiDevPage.do) |
| S10 | 상가(상권)정보 API | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15012005/openapi.do) |
| S11 | 서울 상권분석 데이터·추정매출 | FILE | 불필요 | [공식 안내](https://data.seoul.go.kr/dataList/OA-15572/A/1/datasetView.do) |
| S12 | 학교알리미 Open API | API | SCHOOLINFO_API_KEY | [공식 안내](https://www.schoolinfo.go.kr/ng/go/pnnggo_a01_l0.do?schulCode=S010002286) |
| S13 | TAGO 버스정류소정보 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15098534/openapi.do) |
| S14 | 건축물대장 등본·초본 발급/열람 | FILE | 불필요 | [공식 안내](https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=15000000098) |
| S15 | 등기사항증명서 열람·발급 | FILE | 불필요 | [공식 안내](https://www.iros.go.kr/) |
| S16 | 전세보증금반환보증 안내·제출서류 | FILE | 불필요 | [공식 안내](https://m.khug.or.kr/hug/web/ig/dr/igdr000001.jsp?tabMenu=Y) |
| S17 | 국가법령정보 공동활용 API | API | LAW_OC | [공식 안내](https://open.law.go.kr/LSO/openApi/openApiManual.do) |
| S18 | 토지이음 열람·고시정보 | FILE | 불필요 | [공식 안내](https://www.eum.go.kr/web/am/amMain.jsp) |
| S19 | 건축HUB 건축인허가정보 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15136267/openapi.do) |
| S20 | LH 분양임대공고문 조회 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15058530/openapi.do) |
| S21 | 네이버페이 부동산 현재 매물 | BROWSER | 불필요 | [공식 안내](https://fin.land.naver.com/) |
| S22 | 한국은행 ECOS Open API | API | ECOS_API_KEY | [공식 안내](https://ecos.bok.or.kr/api/) |
| M01 | 고객 목적·자금·선호 | MANUAL | 불필요 | 개인정보 없는 사용자 정리표 |
| M02 | 보유 매물·경쟁 매물·상담 기록 | MANUAL | 불필요 | 개인정보 없는 사용자 정리표 |
| M03 | 임대차·관리비·수금·운영 원장 | MANUAL | 불필요 | 개인정보 없는 사용자 정리표 |
| M04 | 권한·기존 임대차·추가 계약 자료 | MANUAL | 불필요 | 개인정보 없는 사용자 정리표 |
| M05 | 현장 조사·시설 상태 | MANUAL | 불필요 | 개인정보 없는 사용자 정리표 |
| M06 | 금융·세무·공사 등 개별 견적 | MANUAL | 불필요 | 개인정보 없는 사용자 정리표 |
| M07 | 설계·측량·인허가 사전 확인 | MANUAL | 불필요 | 개인정보 없는 사용자 정리표 |
| M08 | 점포 사업 가정·실매출 | MANUAL | 불필요 | 개인정보 없는 사용자 정리표 |
