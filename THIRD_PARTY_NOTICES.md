# 외부 자료와 의존성

- Python: Python Software Foundation License — https://docs.python.org/3/license.html
- pypdf: BSD-3-Clause — https://github.com/py-pdf/pypdf/blob/main/LICENSE
- Playwright: Apache-2.0 — https://github.com/microsoft/playwright/blob/main/LICENSE
- pdf-lib: MIT — https://github.com/Hopding/pdf-lib/blob/master/LICENSE.md
- Node.js 및 설치 브라우저는 각 제품의 이용 조건을 따릅니다. 실행 프로그램·브라우저·OS 글꼴은 이 압축파일에 포함하지 않습니다.
- 예시의 리포트 문장·도식은 프로젝트 제작물입니다. 인용한 사실은 예시 내부 기관명·링크·기준일과 references/research-register.json을 참조하세요. 외부 보고서 PDF·부동산 사진·고객 후기 원문은 묶어 배포하지 않습니다.
- 회귀 테스트의 공개 API 응답 표본은 해당 제공기관의 자료로, 운영 성공/현재 상태를 보증하는 자료가 아닙니다. 실제 표본을 재생하는 테스트와 합성 테스트를 구분합니다.
- 공개본에는 실제 인증값을 포함하지 않습니다. 각 사용자가 서비스 계정·활용승인·인증키를 설정하며 제공기관의 호출 한도와 이용 조건이 적용됩니다.

- `assets/cover-v.png`: 본 프로젝트에서 OpenAI image generation 도구로 생성한 추상 건축 이미지. 실제 부동산 외관이나 조망 사진이 아니며 분석 근거로 사용하지 않습니다. V안 표지 장식용으로 포함합니다. 글꼴은 포함하지 않고 설치된 한국어 글꼴을 사용합니다.

## 2.2.0에 포함한 원본 스킬

- VWorld: https://github.com/clazic/vworld — MIT, `vendor/vworld/LICENSE`. 0.3.5 실행파일은 최초 설치 시 공식 릴리스에서 받으며 해시를 확인합니다. 배포 체크섬은 `vendor/vworld/release-0.3.5/SHA256SUMS`입니다.
- korean-humanizer: 원본 저장소·고정 커밋·개별 파일 해시는 `references/integrations-lock.json`에 기록. MIT, `vendor/korean-humanizer/LICENSE`.
- scientific-visualization: https://github.com/K-Dense-AI/claude-scientific-skills — MIT, `vendor/scientific-visualization/LICENSE.md`. 해당 스킬 폴더의 고정 원본을 포함합니다.
- 위 MIT 구성요소에는 각각의 MIT 조건이 적용되며 EZIWORK의 스킬 재판매 제한을 덧씌우지 않습니다. 원본과 EZIWORK 어댑터는 별도 파일입니다.
- Matplotlib 3.10.7: PSF 기반 Matplotlib License, https://matplotlib.org/stable/project/license.html
- Pillow 12.3.0: MIT-CMU / HPND, https://pillow.readthedocs.io/en/stable/about.html
- pypdf 6.10.0: BSD-3-Clause. 직접 의존성 버전을 고정하고 설치된 전이 의존성 버전은 검증 환경 목록에 기록합니다.
- VWorld 지도와 좌표 응답은 VWorld의 데이터·지도 이용 조건이 별도로 적용됩니다. 지도 원본 출처 표시를 유지합니다. 이번 지도는 주소 조회점과 배경지도이며 동호실 위치·필지 경계를 증명하지 않습니다.

scientific-visualization 원본이 요청하는 소프트웨어 문헌 표기: Timothy Kassis, Vinayak Agarwal, Yuhuan He, Darshil Patel, Aubrey M. Brueckner (2026), *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. https://doi.org/10.48550/arXiv.2609.00065 . 이는 스킬 라이브러리 출처이며 개별 부동산 분석의 검증 근거는 아닙니다.
