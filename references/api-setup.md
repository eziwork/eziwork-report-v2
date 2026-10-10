# API 설정과 복구 · 2.3.2

## 실행 전 기본 키 점검

    python scripts/eziwork.py key-env check
    python scripts/eziwork.py key-env setup

공공데이터포털·VWorld·KOSIS·R-ONE·ECOS 5개 환경 설정을 모두 확인한다. check는 네트워크 호출 없이 저장 여부·적용 위치·설정 충돌·누락 목록만 출력한다. 새 고객 보고서는 5개 등록 전 수집·초안을 시작하지 않는다. 등록 완료가 API 인증·활용승인 성공은 아니다.

setup은 사용자 저장소에 없는 값 중 현재 프로세스 또는 기존 로컬 값은 재입력 없이 이전한다. 실제 누락 키만 별표와 입력 글자 수가 표시되는 터미널에서 받는다. EZIWORK local-credentials.json에 해당 값이 있으면 저장 위치를 안내하고 이전한다. 기존 프로세스/저장 환경값은 자동으로 덮어쓰지 않는다. 취소 전에 저장한 값은 유지하며 다음 실행에서 누락 항목만 이어서 입력한다. 키를 채팅·명령 인수·보고서에 넣지 않는다. 안전한 숨김 입력을 지원하지 않는 터미널에서는 중단한다.

Windows: HKCU Environment의 현재 사용자 환경변수에 저장하고 저장값을 직접 확인한다. 다른 앱은 재시작해야 상속할 수 있다.
Mac: ~/.config/eziwork-report-v2/environment.json을 사용자 전용 권한(파일0600/폴더0700)으로 저장하고 EZIWORK 실행 프로세스에 적용한다. 모든 앱의 전역 환경변수가 아니며 셸 시작 파일을 수정하지 않는다. Mac 실기 검증 여부는 검증표를 참조한다.

우선순위는 프로세스 환경변수 → Windows 사용자 또는 Mac 전용 저장값이다. 서로 다르면 conflict를 표시하고 프로세스 값이 우선한다. 키를 교체하려면 key-env window --name ECOS_API_KEY --replace 또는 key-env setup --name ECOS_API_KEY --replace를 사용한다. 기존 부모 프로세스에 예전 값이 남아 conflict가 표시되면 앱/터미널 재시작 후 check한다. 저장값을 바꾸기 위해 키를 다시 발급받을 필요는 없다. 과거 configure로 저장된 로컬 파일은 이전용이다. key-env ensure/setup이 사용자 저장소로 이전한다. 현재 configure는 사용자 저장소에 저장하는 호환 명령이며 해당 키를 새로 입력받는다. 상대 EZIWORK_CREDENTIAL_FILE 경로는 작업 프로젝트가 아닌 설치된 스킬 폴더를 기준으로 해석한다.

설치 점검, 자료 검토, 합성 시험, 과거 완성 HTML의 PDF 변환은 키 등록과 분리한다. 고객용 신규 파일 입력 보고서는 5개 등록 기준을 적용한다.

| 설정 | 공식 신청·안내 | 등록 후 확인 |
|---|---|---|
| DATA_GO_KR_SERVICE_KEY | [공공데이터포털](https://www.data.go.kr/) | 필요한 서비스별 활용신청·승인, 동일 키의 서비스별 권한 |
| VWORLD_API_KEY | [VWorld](https://www.vworld.kr/) | 사용 API·도메인 제한, 필요하면 VWORLD_DOMAIN 별도 설정 |
| KOSIS_API_KEY | [KOSIS OpenAPI](https://kosis.kr/openapi/) | 통계표·항목·지역·주기·기간·단위 |
| RONE_API_KEY | [R-ONE](https://www.reb.or.kr/r-one/portal/openapi/openApiDevPage.do) | 통계표·분류·항목·주기·기간·단위 |
| ECOS_API_KEY | [ECOS](https://ecos.bok.or.kr/api/) | 통계코드·항목·주기·기간·단위 및 메타데이터 |

선택한 출처만 preflight → collect한다. sources가 없으면 조회 조건 보완 상태로 멈춘다. 활용신청·CAPTCHA·기관 약관 절차는 제공기관 화면에서 완료한다.

| 상태 | 처리 |
|---|---|
| KEY_INPUT_REQUIRED | 누락된 키를 key-env setup으로 등록 |
| KEY_STORE_REVIEW_REQUIRED | 저장소 읽기·권한·형식 확인. 키 값은 출력하지 않음 |
| KEYS_PRESENT_NOT_VERIFIED | 5개 저장만 확인. 실제 인증·서비스 승인 확인 필요 |
| AUTH_REJECTED / AUTH_APPROVAL_REQUIRED | 키 형식·승인·허용 도메인 확인. 인증 오류 반복 호출 금지 |
| CREDENTIAL_EXPIRED_CONFIRMED | 제공기관이 만료를 명시한 경우에만 갱신 안내 |
| REQUEST_CONFIG_INVALID / PARAMS_REQUIRED | 공식 표·항목·지역·기간·단위 코드 재확인 |
| RATE_LIMITED / TIMEOUT / SERVER_UNAVAILABLE | 일시 오류만 최대 3회. 실패 기록과 재개 위치 보존 |
| STATISTIC_METADATA_REQUIRED | 응답 누락 식별 필드의 공식 메타데이터 확보 |
| INPUT_REQUIRED / BROWSER_REQUIRED | 공식 파일 입력 또는 연결 브라우저 필요 |
| 정상 0건 | 성공한 조회 범위에서 0건. 미수집·실패와 구분 |

학교·법령·주소의 대체 접수 및 과거 기록 이전은 [공식 자료 안내](public-evidence.md), 통계 범위는 [통계 검증 안내](statistics-scope.md)를 따른다. 제외된 세 서비스의 과거 정의는 legacy 폴더에만 보존하며 새 발급이나 API 호출을 안내하지 않는다. 공유 외부 설정 파일·다른 프로그램에서 쓰는 키·시스템 환경변수·발급기관의 키는 삭제하지 않는다.

공개 패키지에 인증값을 넣지 않는다. config/default-credentials.json은 빈 객체다.

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
| S07 | VWorld 주소·좌표 확인 | API | VWORLD_API_KEY | [공식 안내](https://www.vworld.kr/) |
| S08 | KOSIS 통계자료·공유서비스 | API | KOSIS_API_KEY | [공식 안내](https://kosis.kr/openapi/devGuide/devGuide_0201List.do) |
| S09 | 부동산통계(R-ONE) 조회 | API | RONE_API_KEY | [공식 안내](https://www.reb.or.kr/r-one/portal/openapi/openApiDevPage.do) |
| S10 | 상가(상권)정보 API | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15012005/openapi.do) |
| S11 | 서울 상권분석 데이터·추정매출 | FILE | 불필요 | [공식 안내](https://data.seoul.go.kr/dataList/OA-15572/A/1/datasetView.do) |
| S12 | 공식 학교 위치·학구·배정 공고 | FILE | 불필요 | [공식 안내](https://schoolzone.emac.kr/) |
| S13 | TAGO 버스정류소정보 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15098534/openapi.do) |
| S14 | 건축물대장 등본·초본 발급/열람 | FILE | 불필요 | [공식 안내](https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=15000000098) |
| S15 | 등기사항증명서 열람·발급 | FILE | 불필요 | [공식 안내](https://www.iros.go.kr/) |
| S16 | 전세보증금반환보증 안내·제출서류 | FILE | 불필요 | [공식 안내](https://m.khug.or.kr/hug/web/ig/dr/igdr000001.jsp?tabMenu=Y) |
| S17 | 법령·조문·지역별 이용 조건 원문 | FILE | 불필요 | [공식 안내](https://www.law.go.kr/) |
| S18 | 토지이음 열람·고시정보 | FILE | 불필요 | [공식 안내](https://www.eum.go.kr/web/am/amMain.jsp) |
| S19 | 건축HUB 건축인허가정보 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15136267/openapi.do) |
| S20 | LH 분양임대공고문 조회 | API | DATA_GO_KR_SERVICE_KEY | [공식 안내](https://www.data.go.kr/data/15058530/openapi.do) |
| S21 | 네이버페이 부동산 현재 매물 | BROWSER | 불필요 | [공식 안내](https://fin.land.naver.com/) |
| S22 | 한국은행 ECOS Open API | API | ECOS_API_KEY | [공식 안내](https://ecos.bok.or.kr/api/) |
| M01 | 고객 목적·자금·선호 | MANUAL | 불필요 | [공식 안내]() |
| M02 | 보유 매물·경쟁 매물·상담 기록 | MANUAL | 불필요 | [공식 안내]() |
| M03 | 임대차·관리비·수금·운영 원장 | MANUAL | 불필요 | [공식 안내]() |
| M04 | 권한·기존 임대차·추가 계약 자료 | MANUAL | 불필요 | [공식 안내]() |
| M05 | 현장 조사·시설 상태 | MANUAL | 불필요 | [공식 안내]() |
| M06 | 금융·세무·공사 등 개별 견적 | MANUAL | 불필요 | [공식 안내]() |
| M07 | 설계·측량·인허가 사전 확인 | MANUAL | 불필요 | [공식 안내]() |
| M08 | 점포 사업 가정·실매출 | MANUAL | 불필요 | [공식 안내]() |

## 자동 입력 창과 다른 프로젝트에서의 실행

모든 명령은 설치된 스킬의 `scripts/eziwork.py` 절대 경로로 실행한다. `key-env check`는 프로세스뿐 아니라 Windows 사용자 저장소/Mac 공통 저장소도 확인한다. 같은 사용자 저장값은 프로젝트가 달라도 다시 입력받지 않는다. 프로세스에만 있는 값은 `not_persistent`로 구분한다.

- `key-env ensure`: 기존 값 이전 → 실제 누락 시 입력 창 자동 열기. 값은 명령 인수로 전달하지 않는다.
- `key-env window`: 누락 키 입력 창 열기. Windows 별도 콘솔, macOS Terminal을 사용한다.
- `key-env setup`: 현재 대화형 터미널에서 입력. 별표·글자 수·저장 완료 표시. 파이프 입력은 거절한다.
- `key-env setup --name ECOS_API_KEY --replace`: 지정한 키를 명시적으로 교체한다.

`INPUT_WINDOW_OPENED`는 입력 대기이며 완료가 아니다. 창을 중복으로 열지 않는다. 입력/취소 후 check하고 같은 report-job의 status에서 남은 작업을 이어간다. 창 실행 실패는 `INPUT_WINDOW_OPEN_FAILED`, 미지원 환경은 `AUTOMATIC_TERMINAL_UNSUPPORTED`다. 이때만 수동 setup을 안내한다. 자동 창에는 실제 키를 화면이나 로그에 출력하는 기능이 없다. 붙여넣기 확인은 별표·글자 수로 제공한다.
