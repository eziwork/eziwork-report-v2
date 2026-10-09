# EZIWORK Report V2

Codex에서 14종 부동산 고객 상담 리포트를 만드는 소스 공개 스킬입니다. 자연어 요청, 공공자료·개인정보 없는 첨부, 고객 설명형 문장, 근거 시각화, HTML·PDF를 연결합니다. 고객 상담과 유료 리포트 제작은 허용하며 스킬 자체 재판매는 제한합니다. [이용 조건](LICENSE.md)을 확인하세요.

공개본에는 실제 API 인증키가 없습니다. 필요한 키는 [발급·등록 안내](references/api-setup.md)에 따라 등록하세요. 키 없이도 합성 예시와 파일 입력을 사용할 수 있습니다.

## 설치 — Windows / Mac
1. 이 폴더 전체를 Codex가 읽는 프로젝트 `.agents/skills/eziwork-report-v2` 또는 개인 `~/.agents/skills/eziwork-report-v2`에 둡니다. 기존 이름의 스킬을 덮어쓰지 않습니다. 설치 위치는 [공식 스킬 안내](https://learn.chatgpt.com/docs/build-skills)의 로컬 스킬 기준을 따릅니다.
2. Python 3.11 이상, Node.js 20 이상, Chrome/Edge 또는 Playwright Chromium을 준비합니다. 터미널에서 이 폴더로 이동합니다.
3. Windows: `python -m venv .venv` 후 `.venv\Scripts\python -m pip install -r requirements.txt`. Mac: `python3 -m venv .venv` 후 `.venv/bin/python -m pip install -r requirements.txt`.
4. 이후 안내의 `python`은 Windows에서 `.venv\Scripts\python`, Mac에서 `.venv/bin/python`으로 바꾸어 실행합니다. 가상환경을 활성화한 경우에는 `python`을 그대로 사용할 수 있습니다.
5. `npm ci`를 실행합니다. 설치된 Chrome/Edge가 없으면 `npx playwright install chromium`을 실행합니다. 한글 글꼴은 Windows 맑은 고딕, Mac Apple SD Gothic Neo를 우선 사용합니다. 브라우저가 다르면 `HTML_PDF_BROWSER`로 지정할 수 있습니다.
6. 가상환경의 Python으로 `scripts/eziwork.py doctor`를 실행합니다. 필요한 키·브라우저 상태를 확인하되 키 값은 출력하지 않습니다.
7. Codex에서 `$eziwork-report-v2 잠실엘스 84㎡와 리센츠의 최근 가격과 입주 조건을 비교해줘`처럼 요청합니다.

자동 예약 수집이나 별도 유료 AI 호출은 없습니다. Codex 사용 환경·계정·연결 브라우저는 별도 필요합니다. 오프라인에서는 제공자료나 명시된 재생 예시만 사용할 수 있습니다.

## 결과와 수정
기본은 질문에 맞는 HTML과 PDF입니다. 상호·담당자·연락처·로고는 config/branding.example.json을 복사해 설정합니다. 외부에 공개할 업무용 정보만 넣으세요. 작성 중에는 부분 수정·초안 검토도 가능합니다. 새 실행/수정은 새 출력 폴더로 보존합니다.

- [API 키 없이 첫 출력 확인](examples/quickstart/README.md)
- [14종 요청 예시](examples/requests.md)
- [제작 기준표](references/catalog.html)
- [첨부 자료와 개인정보 안내](references/attachments.md)
- [API 설정/실패 안내](references/api-setup.md)
- [실행 인터페이스](references/workflow.md)
- [검증 결과와 미검증 범위](qa/release-status.json)

샘플은 기준일의 공개 사례 재생이며 현재 매물·모집 안내가 아닙니다. 합성 테스트는 실제 수집 성공으로 집계하지 않습니다. Windows 검증과 Mac 실기 검증을 분리해 표시합니다.

## V안 시작·끝 표지 (2.1.0)

완성 리포트에 사선 건축 이미지와 청회색 제목, 노란 사선을 사용한 표지를 기본 적용합니다. 대상·기준일·상담 정보가 보고서마다 바뀝니다. [설정과 출력 방법](references/cover-v.md) · [P01 HTML 예시](examples/P01/report-v.html) · [P01 PDF 예시](examples/P01/report-v.pdf). 14종 각 예시 폴더의 `report-v.html/pdf`에서 확인할 수 있습니다. 기존 본문 기준본은 그대로 보존합니다.
