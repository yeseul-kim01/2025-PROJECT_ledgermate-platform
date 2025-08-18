# LedgerMate — Policy Parser Prep (MVP)

학생회 예·결산 규정 문서를 **Upstage Document Digitization API**로 파싱하고, 결과 JSON을 저장/검토하기 위한 최소 도구입니다.
DB 적재 전 단계에서 **품질 확인과 재현성**에 집중합니다.

## Repo 구조

```
LEDGERMATE/
├─ packages/
│  ├─ lm-core-schema/           # 공통 스키마 (pydantic 등)
│  ├─ lm-docparse/
│  │  └─ lm_docparse/pdfParser.py  # ← Upstage API 호출 함수 (call_document_parse)
│  └─ lm-store/                 # (추후) 저장소 어댑터
├─ examples/
│  ├─ parse_policies.py         # Typer CLI (one, batch)
│  └─ parse_one_debug.py        # 디버그 러너(직접 호출)
├─ data/
│  └─ policies-sample/          # 샘플 규정 PDF/HWP (커밋 가능)
├─ local/                        # 실제 문서(커밋 금지)
│  └─ policies/
├─ out/                          # 출력 JSON 등(커밋 금지)
├─ .venv/                        # Python 3.11 venv
├─ requirements/                 # (선택) 분리형 요구사항
└─ README.md
```

## 빠른 시작 (Python 3.11)

```bash
# 0) 가상환경
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

# 1) 의존 설치 (editable)
pip install -e ./packages/lm-core-schema -e ./packages/lm-docparse -e ./packages/lm-store
# 또는 requirements가 있다면
# pip install -r requirements/dev.txt

# 2) 환경변수 (.env)
cp .env.example .env   # 파일 만든 후 키 채우기
```

`.env.example`

```
UPSTAGE_API_KEY=YOUR_KEY
# 기본값: https://api.upstage.ai/v1
PARSER_API_BASE=https://api.upstage.ai/v1
```

## 사용법

### 1) 단일 파일 파싱

```bash
source .venv/bin/activate
python examples/parse_policies.py one \
  "data/policies-sample/부산대학교 총학생회 재정운용세칙.pdf" \
  --out "out/policies/부산.json" \
  --formats html --formats text \
  -v
```

* `--formats`는 `html`, `text`, `markdown` 중 선택 (여러 번 지정 가능)
* `-v`로 업로드/옵션/소요시간 로그 출력

### 2) 배치 파싱

```bash
python examples/parse_policies.py batch \
  "data/policies-sample/*.pdf" \
  --out-dir "out/policies" \
  --formats html --formats text -v
```

### 3) 디버그 러너 (직접 호출)

```bash
python examples/parse_one_debug.py
```

* `.env` 키 확인, 입력/출력 경로, 호출 로그가 순서대로 출력됩니다.

> **출력**은 모두 `out/` 아래에 저장됩니다. 경로에 맞는 폴더가 없으면 자동 생성합니다.

## 자주 쓰는 옵션 가이드

* `ocr`: `force`(스캔 PDF에 유리) / `auto`(텍스트 PDF면 빠르고 저렴)
* `coordinates`: 바운딩 박스 좌표 필요 시 `True`
* `chart_recognition`: 차트가 많은 문서면 `True` 유지
* `timeout`: `(connect, read)` 튜플로 분리해도 됨 (코드에서 지원)

## 트러블슈팅

* **아무 출력도 안 나옴**

  * `examples/parse_policies.py` 맨 아래 `if __name__ == "__main__": app()` 있는지 확인
  * `-v`(verbose)로 실행
  * `which python` → `.venv/bin/python`인지 확인

* **ModuleNotFoundError: lm\_docparse**

  * `pip install -e ./packages/lm-docparse` 실행
  * `packages/lm-docparse/pyproject.toml` 존재/경로 확인
  * 패키지 폴더는 `lm_docparse/`(언더스코어)여야 함

* **pyproject.toml not found**

  * 위치가 `packages/lm-docparse/pyproject.toml`(바로 아래)인지 확인
  * 필요 시 `setup.py` 간이 파일로 대체 가능

* **FileNotFoundError (저장 경로)**

  * `out/` 폴더 자동 생성되도록 구현되어 있음. 그래도 나면 경로 오타 확인

* **Timeout/ConnectionError**

  * 네트워크/프록시/VPN 이슈 가능 → 개인망/테더링 시도
  * `ocr="auto"`로 테스트 (처리시간 단축)
  * `timeout` 읽기 값을 늘림(예: `(15, 180)`)

* **HTTP 401/403**

  * `.env`의 `UPSTAGE_API_KEY` 값/개행/공백 확인
  * 헤더 `"Authorization": "Bearer <KEY>"` 형식 유지 (코드 기본 OK)

* **HTTP 404/422**

  * 엔드포인트/파라미터 재확인
  * `--formats text` 등 최소 옵션으로 먼저 테스트

## 커밋 위생

`.gitignore` 예시:

```
.venv/
.env
out/
local/
__pycache__/
*.log
*.cache
```

샘플/공개 가능 파일은 `data/`에, 실제 문서는 `local/`에 두고 **커밋 금지**.

## 다음 단계(로드맵: DB 이전)

* [ ] `preview` 커맨드: 저장된 JSON을 조항 단위로 요약 출력
* [ ] `preflight` 커맨드: 청크 통계(빈/중복/헤더푸터 의심), 게이트 결과(`ready/needs_review`) 저장
* [ ] 규정 청크 정규화: 하이픈 줄바꿈 복원, 페이지 헤더/푸터 제거
* [ ] DB 적재 CLI(`policy-index`): **승인된 플랜**만 반영하도록 분리
* [ ] (선택) 재시도/백오프(tenacity), 입력 파일 해시 기반 스킵

## 라이선스 / 문의

* License: TBA
* Maintainer: TBA

---

필요하면 `preview`/`preflight` 커맨드까지 바로 넣은 버전으로 README를 업데이트해줄게. 지금은 **현재 돌아가는 기능 위주**로 깔끔하게 정리했어.
