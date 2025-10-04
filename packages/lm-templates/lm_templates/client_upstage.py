# examples/ingest_settlement_template.py
import json, hashlib, sys, os
from lm_docparse.pdfParser import call_document_parse      # ⬅️ 이걸 사용
from lm_templates.detector import detect_template_from_html

def file_id_of(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def extract_html(resp: dict) -> str:
    """Upstage 응답에서 HTML을 안전하게 추출"""
    if not isinstance(resp, dict):
        return ""
    if isinstance(resp.get("html"), str):
        return resp["html"]
    if isinstance(resp.get("data"), str):
        return resp["data"]
    for k in ("results", "documents", "outputs"):
        arr = resp.get(k)
        if isinstance(arr, list):
            for x in arr:
                if isinstance(x, dict) and isinstance(x.get("html"), str):
                    return x["html"]
    content = resp.get("content")
    if isinstance(content, str) and "<html" in content.lower():
        return content
    return ""

def main(pdf_path: str, out_path: str = "out/templates/template.json"):
    # Upstage Document Parsing 호출 (원 응답 raw도 파일로 저장)
    raw_out = out_path.replace(".json", ".raw.json")
    resp = call_document_parse(
        input_file=pdf_path,
        output_file=raw_out,        # 원 응답 JSON 보관
        ocr="auto",
        coordinates=True,
        chart_recognition=False,
        output_formats=["html"],
        base64_encoding=[],
        model="document-parse",
        timeout=120,
        verbose=True,
    )

    html = extract_html(resp)
    if not html:
        print("[ERROR] Upstage 응답에서 HTML을 찾지 못했습니다.")
        print(" → 원 응답:", raw_out)
        print(" → keys:", list(resp.keys()) if isinstance(resp, dict) else type(resp))
        sys.exit(1)

    schema = detect_template_from_html(file_id_of(pdf_path), html)

    # 출력 저장
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, default=lambda o: o.__dict__, ensure_ascii=False, indent=2)

    # 콘솔 프린트
    print(json.dumps(schema, default=lambda o: o.__dict__, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "data/templates-sample/결산안예시.pdf"
    out = sys.argv[2] if len(sys.argv) > 2 else "out/templates/template.json"
    main(pdf, out)
