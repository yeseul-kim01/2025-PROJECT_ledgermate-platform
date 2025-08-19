from __future__ import annotations
import os, argparse, pathlib, json
from dotenv import load_dotenv

from lm_store.pg import (
    connect, ensure_budget_schema, register_artifact,
    create_budget_doc, insert_budget_chunks
)
from lm_docparse.pdfParser import call_document_parse
from lm_docparse.chunker import to_chunks

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="예산안 PDF 경로")
    ap.add_argument("--org-id", required=True)
    ap.add_argument("--title", default="예산안")
    ap.add_argument("--period-from", default=None)
    ap.add_argument("--period-to", default=None)
    ap.add_argument("--policy-id", default=None)
    ap.add_argument("--parse", action="store_true", help="Upstage로 파싱 JSON도 저장")
    ap.add_argument("--created-by", default=None)
    ap.add_argument("--chunk", action="store_true", help="파싱 JSON으로부터 청크 생성/저장")
    args = ap.parse_args()

    pdf_path = pathlib.Path(args.pdf)
    if not pdf_path.exists():
        raise SystemExit(f"❌ No such file: {pdf_path}")

    with connect() as conn:
        ensure_budget_schema(conn)

        # 1) PDF artifact
        pdf_bytes = pdf_path.read_bytes()
        pdf_art = register_artifact(
            conn,
            org_id=args.org_id, kind="raw_pdf",
            filename=pdf_path.name, content=pdf_bytes, mime="application/pdf"
        )
        print("✔ PDF artifact:", pdf_art)

        # 2) (옵션) 파싱 JSON artifact + 객체
        json_art = None
        parsed_obj = None
        if args.parse:
            out_tmp = pdf_path.with_suffix(".parsed.json")
            call_document_parse(str(pdf_path), str(out_tmp))
            jb = out_tmp.read_bytes()
            json_art = register_artifact(
                conn,
                org_id=args.org_id, kind="parse_json",
                filename=out_tmp.name, content=jb, mime="application/json"
            )
            print("✔ PARSE artifact:", json_art)
            try:
                parsed_obj = json.loads(jb.decode("utf-8"))
            except Exception as e:
                print("⚠ 파싱 JSON 디코딩 실패:", e)

        # 3) budget_doc 생성
        bid = create_budget_doc(
            conn,
            org_id=args.org_id, title=args.title,
            period_from=args.period_from, period_to=args.period_to,
            policy_id=args.policy_id, source_pdf_id=pdf_art,
            parsed_json_id=json_art, created_by=args.created_by
        )
        print("✅ budget_doc:", bid)

        # 4) (옵션) 청크 생성/저장
        if args.chunk:
            if parsed_obj is None:
                print("ℹ --chunk 지정됨. parsed_obj가 없어 즉석 파싱을 스킵합니다. (--parse 같이 쓰는 걸 권장)")
            else:
                chunks = to_chunks(parsed_obj)
                count = insert_budget_chunks(
                    conn,
                    budget_doc_id=bid,
                    org_id=args.org_id,
                    policy_id=args.policy_id,
                    chunks=chunks
                )
                print(f"🧩 chunks inserted: {count}")

if __name__ == "__main__":
    main()
