# Windows · macOS 설치

이 폴더를 Codex skills 폴더의 `eziwork-report-v2`에 놓고 Codex를 다시 열어 `$eziwork-report-v2`를 사용합니다. 다른 개인 스킬 설치는 필요하지 않습니다. Python 3.12 이상과 Node.js 22를 준비합니다.

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

지도 인증키는 다음 명령의 숨김 입력으로 저장합니다. 키를 명령에 붙여 쓰지 않습니다.
```
python scripts/eziwork.py configure --name VWORLD_API_KEY
```
Mac에서는 python 대신 python3을 사용할 수 있습니다. 개인 환경변수·로컬 키가 우선하며 키 발급과 도메인 설정은 [API 안내](references/api-setup.md)를 따릅니다. 지도 없이도 저장된 예시 HTML·PDF를 열 수 있습니다. 원자료 없는 분석은 자동으로 채우지 않습니다.

설치 뒤 “이 매물의 가격과 입주 조건을 비교해 리포트를 만들어줘”처럼 요청합니다. Codex가 필요한 근거를 확인하고 지도·그래프·한국어 교정의 적용 여부를 기록합니다. 이미 존재하는 출력 폴더는 덮어쓰지 않고 새 버전으로 저장합니다.

Windows 실제 출력 확인, Mac 자동 검사 정의 및 Mac 실제 실행 대기는 [검증표](qa/integration-2.2.0.md)에 구분했습니다. Mac 지원 검증 완료를 뜻하지 않습니다.
