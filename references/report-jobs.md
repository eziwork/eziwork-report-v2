# 보고서 작업과 완료 기록

명령의 `<CLI>`는 설치된 스킬의 `scripts/eziwork.py` 절대 경로다. 프로젝트의 상대 경로로 실행하지 않는다. 경로에 공백이 있으면 따옴표로 감싼다. 출력과 작업 파일은 고객 프로젝트에 저장한다.

```text
python <CLI> report-job start --request request.json --job output/v01/job.json
python <CLI> report-job status --job output/v01/job.json
python <CLI> report-job bind --job output/v01/job.json --contract report.json
python <CLI> render --contract report.json --output output/v01/files --pdf
python <CLI> report-job finish --job output/v01/job.json --html output/v01/files/report.html --pdf output/v01/files/report.pdf --reviewed
```

request.json에는 수집 조건 외에 원래 고객 질문 `question`, `report_type`, `target`을 보존한다. bind 시 원고의 question·report_id·target·mode와 대조한다. actual은 기본값이다. 합성 시험은 start에 `--mode synthetic_test`, 과거 재생은 `--mode historical_replay`를 명시하며 실제 자료로 바꾸어 표시하지 않는다.

작업 시작/재개 시 키·출력 의존성을 확인한다. 기존 사용자 저장값을 다시 묻지 않고 누락 키만 별도 창에서 받는다. 환경 점검 실패와 근거 부족은 원인을 해결한 뒤 같은 작업에서 재개한다. 작업 파일이 있다고 수집 검증을 생략하지 않는다.

`EVIDENCE_AND_DRAFT_REQUIRED` → `OUTPUT_REQUIRED` → `COMPLETED`로 진행한다. start/bind/status의 `complete:false`와 종료 코드 2는 미완료/진행 중이며 작업 포기를 뜻하지 않는다. 자료 준비와 원고 작성은 Codex가 담당한다. 요청이 변경되면 새 작업 버전을 만든다. 원고가 바뀌면 다시 verify/bind하고 새 출력 버전으로 만든다.

맞춤 HTML은 기존 cover와 원고 대조 후 `pdf --input report.html --output report.pdf --contract report.json`으로 출력한다. PDF 생성 시 HTML·원고의 전후 해시와 PDF 해시를 `<PDF>.delivery.json`에 기록한다. 이 파일은 내부 기록이며 고객 본문에 넣지 않는다. 기존 PDF는 새 기록을 임의 작성하지 말고 현재 HTML에서 재출력한다.

finish는 현재 요청·원고·PDF 출력 기록·HTML/PDF 해시를 대조한다. `--reviewed`는 실제 내용·시각 검토 뒤에만 사용한다. status도 완료 파일의 변경/삭제를 재검사하며 완료 상태를 그대로 신뢰하지 않는다. 새 데이터/원고 변경은 기존 계약 검증을 계속 적용한다. 해시 기록은 자연어 의미나 맞춤 HTML과 계약의 의미 일치를 증명하지 않는다.

최종 답변은 complete:true인 실제 HTML·PDF 링크와 기준일·분석 범위를 전달한다. 작업을 시작하지 않거나 확인 명령을 건너뛰는 에이전트를 이 스크립트가 강제 실행시킬 수는 없다. SKILL.md의 시작·재개·최종 확인 절차를 모두 수행한다. 명시적인 채팅 전용·기획·부분 시안·단일 형식 요청에는 두 파일 완료 절차를 강제하지 않는다.
