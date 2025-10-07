# -*- coding: utf-8 -*-
import json, hashlib, sys, os
from argparse import ArgumentParser
from lm_docparse.pdfParser import call_document_parse
from lm_templates.detector import detect_template_from_html

def file_id_of(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def extract_html(resp: dict) -> str:
    """
    Upstage 응답에서 HTML을 최대한 안전하게 추출한다.
    지원하는 패턴:
    - resp['html'] (string)
    - resp['data'] (string)
    - resp['content']['html'] (dict)
    - resp['content'][i]['html'] (list)
    - resp['elements'][i]['content']['html'] (개별 요소 내 테이블)
    최후수단: elements의 테이블 html을 이어붙여 최소 HTML 문서로 합성.
    """
    if not isinstance(resp, dict):
        return ""

    # 1) 루트 html/data
    if isinstance(resp.get("html"), str) and "<" in resp["html"]:
        return resp["html"]
    if isinstance(resp.get("data"), str) and "<" in resp["data"]:
        return resp["data"]

    # 2) content.*.html
    content = resp.get("content")
    if isinstance(content, dict) and isinstance(content.get("html"), str) and "<" in content["html"]:
        return content["html"]
    if isinstance(content, list):
        for x in content:
            if isinstance(x, dict) and isinstance(x.get("html"), str) and "<" in x["html"]:
                return x["html"]

    # 3) elements[*].content.html (표들이 여기에 담기는 케이스)
    elements = resp.get("elements")
    if isinstance(elements, list):
        parts = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            cnt = el.get("content") or {}
            h = cnt.get("html")
            # 표 단서가 있으면 수집
            if isinstance(h, str) and "<table" in h.lower():
                parts.append(h)
        if parts:
            return "<html><body>\n" + "\n<hr/>\n".join(parts) + "\n</body></html>"

    # 4) content가 문자열이면서 HTML 포함
    if isinstance(content, str) and "<html" in content.lower():
        return content

    return ""

def main(pdf_path: str, out_path: str = "out/templates/template.json", doc_type: str = "settlement"):
    # Upstage Document Parsing 호출 (원 응답 raw도 파일로 저장)
    raw_out = out_path.replace(".json", ".raw.json")
    resp = call_document_parse(
        input_file=pdf_path,
        output_file=raw_out,   # 원 응답 JSON 보관
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

    # (신규) 추출된 HTML도 디스크에 저장 (디버깅/재사용 편의)
    html_out = out_path.replace(".json", ".html")
    os.makedirs(os.path.dirname(html_out), exist_ok=True)
    with open(html_out, "w", encoding="utf-8") as hf:
        hf.write(html)

    schema = detect_template_from_html(file_id_of(pdf_path), html)
    schema.meta["doc_type"] = doc_type  # "budget" | "settlement"

    # 출력 저장
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, default=lambda o: o.__dict__, ensure_ascii=False, indent=2)

    # 콘솔 프린트
    print(json.dumps(schema, default=lambda o: o.__dict__, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("pdf", help="입력 PDF 경로")
    ap.add_argument("out", nargs="?", default="out/templates/template.json", help="출력 JSON 경로")
    ap.add_argument("--doc-type", choices=["budget", "settlement"], default="settlement")
    args = ap.parse_args()
    main(args.pdf, args.out, args.doc_type)
