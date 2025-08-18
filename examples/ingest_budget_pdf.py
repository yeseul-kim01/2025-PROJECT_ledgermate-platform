# examples/ingest_budget_pdf.py
from __future__ import annotations
import os, argparse, pathlib, json
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

from lm_store.pg import connect, ensure_budget_schema, register_artifact, create_budget_doc
from lm_docparse.pdfParser import call_document_parse  # (선택) 파싱 재사용

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="예산안 PDF 경로")
    ap.add_argument("--org-id", required=True)
    ap.add_argument("--title", default="예산안")
    ap.add_argument("--period-from", default=None)  # yyyy-mm-dd
    ap.add_argument("--period-to", default=None)
    ap.add_argument("--policy-id", default=None)
    ap.add_argument("--parse", action="store_true", help="Upstage로 파싱 JSON도 저장")
    ap.add_argument("--created-by", default=None)
    args = ap.parse_args()

    pdf_path = pathlib.Path(args.pdf)
    if not pdf_path.exists():
        raise SystemExit(f"❌ No such file: {pdf_path}")

    with connect() as conn:
        ensure_budget_schema(conn)

        # 1) 원본 PDF artifact
        pdf_bytes = pdf_path.read_bytes()
        pdf_art = register_artifact(conn,
            org_id=args.org_id, kind="raw_pdf",
            filename=pdf_path.name, content=pdf_bytes, mime="application/pdf")
        print("✔ PDF artifact:", pdf_art)

        # 2) (선택) 파싱 JSON artifact
        json_art = None
        if args.parse:
            out_tmp = pdf_path.with_suffix(".parsed.json")
            call_document_parse(str(pdf_path), str(out_tmp))   # 네가 만든 함수
            jb = out_tmp.read_bytes()
            json_art = register_artifact(conn,
                org_id=args.org_id, kind="parse_json",
                filename=out_tmp.name, content=jb, mime="application/json")
            print("✔ PARSE artifact:", json_art)

        # 3) budget_doc 생성
        bid = create_budget_doc(conn,
            org_id=args.org_id, title=args.title,
            period_from=args.period_from, period_to=args.period_to,
            policy_id=args.policy_id, source_pdf_id=pdf_art,
            parsed_json_id=json_art, created_by=args.created_by)
        print("✅ budget_doc:", bid)

if __name__ == "__main__":
    main()
