# 통계 요청과 사용 범위 · 2.3.0

S08 KOSIS: orgId·tblId·itmId·objL1(추가 objL2~8도 요청하면 대조)·prdSe·startPrdDe·endPrdDe·expected_unit.
S09 R-ONE: STATBL_ID·ITM_ID·CLS_ID·DTACYCLE_CD·START_WRTTIME·END_WRTTIME·expected_unit. GRP_ID를 요청하면 함께 대조한다. R-ONE의 MM/QQ/YY/DD를 월/분기/연/일로 해석한다.
S22 ECOS: stat_code·item_code·cycle·start·end·expected_unit. item_code2~4는 순서대로 선택하며 항목 누락으로 차원이 바뀌지 않게 한다.

통계표·지역·항목을 명시하지 않은 ALL/* 요청은 바로 분석하지 않는다. 필요한 범위를 먼저 선택한다. expected_unit은 검토용 필드로 API에 전송하지 않는다. 응답 단위와 정확히 대조한다.

누락 기호(-, … 등)는 결측이며 정상 숫자 0과 구분한다. 음수 통계는 유효할 수 있지만 무한대·NaN은 제외한다. 월·분기·연·일의 날짜 형식과 범위를 대조한다. 지역 통계를 개별 매물의 가격·공실·수익으로 바꾸지 않는다.

## 응답에 식별 필드가 없을 때

추정으로 채우지 않는다. 공식 메타데이터를 확보하고 요청의 scope_evidence에 출처별 근거를 기록한다. 일반 텍스트는 file·sha256·source_url·review_status:VERIFIED·fields·field_quotes를 사용한다. field_quotes는 원문에 실제로 있어야 하며 직접 대조한 내용만 쓴다.

JSON 메타데이터는 rows_path·selector·field_map을 사용한다. selector로 정확히 한 행을 찾고 누락된 필드 값을 대조한다. 예를 들어 ECOS 월별 기준금리는 StatisticItemList 원문에서 STAT_CODE=722Y001, ITEM_CODE=0101000, CYCLE=M 행을 선택해 cycle을 CYCLE과 연결한다. API 키를 metadata URL에 저장하지 않는다.

메타데이터는 수집 실행의 raw 폴더에 복사하고 해시를 보존한다. 원문·검토 규칙이 변경되면 coverage review를 다시 수행한다.

공식 안내: [KOSIS](https://kosis.kr/openapi/devGuide/devGuide_0201List.do), [R-ONE](https://www.reb.or.kr/r-one/portal/openapi/openApiDevPage.do), [ECOS](https://ecos.bok.or.kr/api/).

이번 표본: KOSIS DT_1B040A3 총인구수 T20·서울 11, R-ONE A_2024_00903 전국 지가변동률, ECOS 722Y001 기준금리. 모두 2025년 1~3월. 표본의 값을 보고서 기본값으로 사용하지 않는다.

