# ===============================================
# LedgerMate — 결산안 템플릿 파싱 예제 (API/DB 無)
# -----------------------------------------------
# 목적:
#   - 결산안 PDF를 Upstage Document Parsing(API)로 파싱
#   - 응답(JSON)에서 HTML/Markdown을 안전하게 추출
#   - HTML을 분석해 결산표/헤더를 감지(템플릿 스키마) → JSON 출력/저장
#
# 입력:
#   - argv[1]: 결산안 PDF 경로 (예: data/templates-sample/결산안예시.pdf)
#   - argv[2]: 출력 경로 (예: out/templates/결산안예시.template.json) [선택]
#
# 출력:
#   - <out>.raw.json  : Upstage 원 응답(디버깅용)
#   - <out>.json      : detector 결과(TemplateSchema: 헤더/테이블/표준 컬럼 후보)
#
# 의존성:
#   - pip install -e packages/lm-docparse -e packages/lm-templates
#   - pip install requests python-dotenv beautifulsoup4
#   - env: export UPSTAGE_API_KEY=...
#
# 실행 예:
#   export PYTHONPATH=$(pwd)
#   mkdir -p out/templates
#   python examples/ingest_settlement_template.py \
#     data/templates-sample/결산안예시.pdf \
#     out/templates/결산안예시.template.json
#
# 동작 요약:
#   1) Upstage Document Parsing 호출 (html/markdown/text 요청)
#   2) 응답 JSON에서 재귀로 html/markdown 텍스트를 탐색해 추출
#   3) detector로 결산표/헤더 감지 → TemplateSchema 생성
#   4) 콘솔/파일로 출력
#
# 트러블슈팅:
#   - 401/403: UPSTAGE_API_KEY 확인
#   - [ERROR] HTML… 못 찾음: raw.json 열어 응답 구조 확인 → extract_html 분기 보강
#   - ModuleNotFoundError: 패키지 -e 설치/ PYTHONPATH 확인
#   - FileNotFoundError: 출력 디렉토리 미리 생성 (mkdir -p out/templates)
# ===============================================

import json, hashlib, sys, os
from lm_docparse.pdfParser import call_document_parse
from lm_templates.detector import detect_template_from_html

def file_id_of(path: str) -> str:
    """파일 '내용'으로 SHA1 해시 → 파일 식별자(경로 해시보다 안전)"""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _find_first_html(obj):
    """dict/list/str 전체를 재귀적으로 훑어 최초의 HTML 문자열을 반환"""
    if isinstance(obj, str):
        s = obj.strip()
        if "<html" in s.lower() and "</html>" in s.lower():
            return s
        return None
    if isinstance(obj, dict):
        # 흔한 키 우선 시도
        for k in ("html", "content", "data"):
            if k in obj:
                v = _find_first_html(obj[k])
                if v: return v
        # 그 외 키도 전부 탐색
        for v in obj.values():
            r = _find_first_html(v)
            if r: return r
    if isinstance(obj, list):
        for v in obj:
            r = _find_first_html(v)
            if r: return r
    return None

def extract_html(resp: dict) -> str:
    """응답에서 HTML을 우선 추출, 없으면 길이 있는 Markdown도 대체 허용"""
    # 1) 재귀로 html 찾기
    html = _find_first_html(resp)
    if html:
        return html

    # 2) html 없으면 markdown/text 추정
    def _find_markdown(obj):
        if isinstance(obj, str) and len(obj) > 200 and ("|" in obj or "##" in obj or "**" in obj):
            return obj
        if isinstance(obj, dict):
            for k in ("markdown", "md", "text"):
                if k in obj:
                    v = _find_markdown(obj[k])
                    if v: return v
            for v in obj.values():
                r = _find_markdown(v)
                if r: return r
        if isinstance(obj, list):
            for v in obj:
                r = _find_markdown(v)
                if r: return r
        return None

    md = _find_markdown(resp)
    return md or ""

def main(pdf_path: str, out_path: str = "out/templates/template.json"):
    raw_out = out_path.replace(".json", ".raw.json")

    # Upstage Document Parsing 호출 (원 응답은 raw_out에 저장됨)
    resp = call_document_parse(
        input_file=pdf_path,
        output_file=raw_out,
        ocr="auto",                   # 디지털이면 패스, 스캔이면 OCR
        coordinates=True,             # 좌표 보존(후속 기능 대비)
        chart_recognition=False,      # 차트 인식 불필요
        output_formats=["html", "markdown", "text"],  # html 우선, 대체로 md/text
        base64_encoding=[],           # 테이블 b64 불필요
        model="document-parse",
        timeout=120,
        verbose=True,
    )

    # 응답에서 HTML/Markdown 추출
    html = extract_html(resp)
    if not html:
        print("[ERROR] Upstage 응답에서 HTML/Markdown을 찾지 못했습니다. 원 응답 파일을 확인하세요:", raw_out)
        sys.exit(1)

    # HTML → 템플릿 스키마 감지(헤더, 테이블, 컬럼 표준화 매핑 후보)
    schema = detect_template_from_html(file_id_of(pdf_path), html)

    # 파일 저장
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, default=lambda o: o.__dict__, ensure_ascii=False, indent=2)

    # 콘솔 출력
    print(json.dumps(schema, default=lambda o: o.__dict__, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "data/templates-sample/결산안예시.pdf"
    out = sys.argv[2] if len(sys.argv) > 2 else "out/templates/template.json"
    main(pdf, out)
