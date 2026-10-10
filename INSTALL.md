# Windows · macOS 설치

이 폴더를 Codex skills 폴더의 `real-estate-report`에 놓고 Codex를 다시 열어 `$real-estate-report`를 사용합니다. 다른 개인 스킬 설치는 필요하지 않습니다. Python 3.12 이상과 Node.js 22를 준비합니다.

Windows PowerShell에서 스킬 폴더로 이동한 뒤:
```powershell
python scripts/eziwork.py integrations setup --python
npm ci
npx playwright install chromium
python scripts/eziwork.py doctor
python scripts/eziwork.py integrations check
```

macOS 터미널에서 같은 폴더로 이동한 뒤:
```sh
python3 scripts/eziwork.py integrations setup --python
npm ci
npx playwright install chromium
python3 scripts/eziwork.py doctor
python3 scripts/eziwork.py integrations check
```

설치는 Python 라이브러리와 현재 OS용 VWorld 고정 실행파일을 내려받습니다. VWorld API는 호출하지 않으며 체크섬이 다르면 설치를 멈춥니다. `runtime/`은 로컬 설치물로 GitHub·압축 배포본에는 포함하지 않습니다. Windows는 Malgun Gothic, Mac은 Apple SD Gothic Neo 등을 탐색합니다. 한글 글꼴을 찾지 못하면 `EZIWORK_KOREAN_FONT`에 설치된 글꼴 경로를 설정합니다. 글꼴 자체는 배포하지 않습니다.

새 고객 보고서를 만들기 전 공공데이터포털·VWorld·KOSIS·R-ONE·ECOS 다섯 키를 등록합니다. 이미 저장한 키는 다시 묻지 않습니다. 키 값을 채팅이나 명령 인수에 붙이지 않습니다.

Windows:
~~~powershell
python scripts/eziwork.py key-env check
python scripts/eziwork.py key-env ensure
~~~

macOS:
~~~sh
python3 scripts/eziwork.py key-env check
python3 scripts/eziwork.py key-env ensure
~~~

check는 네트워크를 호출하지 않습니다. setup은 누락값이 있으면 별도 입력 창을 열며 등록 가능한 기존 EZIWORK 설정값이 있으면 저장 위치를 안내하고 이전합니다. Windows는 현재 사용자 환경변수에 저장합니다. Mac은 사용자 전용 ~/.config/eziwork-report-v2/environment.json에 저장하고 스킬 실행 환경에만 적용합니다. 프로세스 환경변수가 우선하며 값이 다르면 충돌을 표시합니다.

다섯 값의 등록과 각 서비스의 인증·활용승인 성공은 별개입니다. 고객 질문에 필요한 출처만 호출합니다. 기존 예시 열기·단순 PDF 변환·합성 시험은 키 등록 없이 가능합니다. 발급·교체·실패 구분은 [API 안내](references/api-setup.md)를 따릅니다.

다른 프로젝트에서는 위 명령의 scripts/eziwork.py를 설치된 스킬의 절대 경로로 바꿉니다. 열린 창에서 별표·입력 글자 수와 저장 완료를 확인합니다. 창 실행이 불가능하면 대화형 터미널에서 key-env setup을 사용합니다.

설치 뒤 “이 매물의 가격과 입주 조건을 비교해 리포트를 만들어줘”처럼 요청합니다. Codex가 필요한 근거를 확인하고 지도·그래프·한국어 교정의 적용 여부를 기록합니다. 이미 존재하는 출력 폴더는 덮어쓰지 않고 새 버전으로 저장합니다.

Windows 실제 출력 확인, Mac 자동 검사 정의 및 Mac 실제 실행 대기는 [2.3.0 검증표](qa/migration-2.3.0.md)에 구분했습니다. Mac 지원 검증 완료를 뜻하지 않습니다.
