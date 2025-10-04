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
import psycopg2  # ← DB 직접 연결용 (pip install psycopg2-binary)

# --- DB 저장 함수 추가 ---
def save_template_to_db(schema_obj, pdf_path: str):
    """
    settlement_template 테이블에 upsert.
    - 연결정보: 환경변수 PG_DSN (예: postgresql://user:pass@localhost:5432/ledgermate)
    - 테이블이 없으면 아래 DDL 참고.
    """
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        print("[WARN] PG_DSN 미설정 → DB 저장 생략")
        return

    # dataclass 포함 객체를 안전하게 직렬화
    payload = json.dumps(schema_obj, default=lambda o: o.__dict__, ensure_ascii=False)

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    # template_id는 파일 '내용' 해시(아래 file_id_of와 동일 로직)로 쓰는 게 안전
    template_id = file_id_of(pdf_path)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settlement_template (
      template_id TEXT PRIMARY KEY,
      file_path   TEXT NOT NULL,
      schema_json JSONB NOT NULL,
      created_at  TIMESTAMPTZ DEFAULT now(),
      updated_at  TIMESTAMPTZ DEFAULT now()
    );
    """)
    cur.execute("""
    INSERT INTO settlement_template (template_id, file_path, schema_json)
    VALUES (%s, %s, %s::jsonb)
    ON CONFLICT (template_id) DO UPDATE
      SET file_path=EXCLUDED.file_path,
          schema_json=EXCLUDED.schema_json,
          updated_at=now()
    """, (template_id, pdf_path, payload))

    cur.close()
    conn.close()
    print(f"✓ DB saved: settlement_template.template_id={template_id}")

def file_id_of(path: str) -> str:
    """파일 '내용'으로 SHA1 해시 → 파일 식별자(경로 해시보다 안전)"""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _find_first_html(obj):
    # ... (네가 가진 함수 그대로)
    if isinstance(obj, str):
        s = obj.strip()
        if "<html" in s.lower() and "</html>" in s.lower():
            return s
        return None
    if isinstance(obj, dict):
        for k in ("html", "content", "data"):
            if k in obj:
                v = _find_first_html(obj[k]);  
                if v: return v
        for v in obj.values():
            r = _find_first_html(v);  
            if r: return r
    if isinstance(obj, list):
        for v in obj:
            r = _find_first_html(v);  
            if r: return r
    return None

def extract_html(resp: dict) -> str:
    # ... (네가 가진 함수 그대로)
    html = _find_first_html(resp)
    if html: return html
    def _find_markdown(obj):
        if isinstance(obj, str) and len(obj) > 200 and ("|" in obj or "##" in obj or "**" in obj):
            return obj
        if isinstance(obj, dict):
            for k in ("markdown", "md", "text"):
                if k in obj:
                    v = _find_markdown(obj[k]);  
                    if v: return v
            for v in obj.values():
                r = _find_markdown(v);  
                if r: return r
        if isinstance(obj, list):
            for v in obj:
                r = _find_markdown(v);  
                if r: return r
        return None
    md = _find_markdown(resp)
    return md or ""

def main(pdf_path: str, out_path: str = "out/templates/template.json"):
    raw_out = out_path.replace(".json", ".raw.json")

    resp = call_document_parse(
        input_file=pdf_path,
        output_file=raw_out,
        ocr="auto",
        coordinates=True,
        chart_recognition=False,
        output_formats=["html", "markdown", "text"],
        base64_encoding=[],
        model="document-parse",
        timeout=120,
        verbose=True,
    )

    html = extract_html(resp)
    if not html:
        print("[ERROR] Upstage 응답에서 HTML/Markdown을 찾지 못했습니다. 원 응답 파일을 확인하세요:", raw_out)
        sys.exit(1)

    schema = detect_template_from_html(file_id_of(pdf_path), html)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, default=lambda o: o.__dict__, ensure_ascii=False, indent=2)

    print(json.dumps(schema, default=lambda o: o.__dict__, ensure_ascii=False, indent=2))

    # 여기서 DB 저장 호출 (스코프 OK)
    save_template_to_db(schema, pdf_path)

if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "data/templates-sample/결산안예시.pdf"
    out = sys.argv[2] if len(sys.argv) > 2 else "out/templates/template.json"
    main(pdf, out)
