# 키 없이 실행하는 설치 확인

아래 `python`은 Windows `.venv\Scripts\python`, Mac `.venv/bin/python`으로 바꾸어 실행합니다.

스킬 폴더에서 실행합니다. 아래 자료는 전부 합성값이며 실제 자산 운영성과가 아닙니다.

```
python scripts/eziwork.py verify --contract examples/quickstart/report.json
python scripts/eziwork.py render --contract examples/quickstart/report.json --output output/first-report --pdf
```

결과는 지정한 폴더에 HTML·PDF로 저장됩니다. 다시 만들 때는 새 출력 폴더를 사용합니다. 실제 리포트는 Codex에 자연어로 요청하고, 수집·첨부 검토를 거쳐 새 계약 자료를 작성합니다. 이 합성 자료를 실제 근거로 바꾸어 표시하지 않습니다.
