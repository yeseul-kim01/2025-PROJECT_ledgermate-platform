from __future__ import annotations
import os, argparse, pathlib, json
from dotenv import load_dotenv

from lm_store.pg import (
    connect, ensure_budget_schema, register_artifact,
    create_budget_doc, insert_budget_chunks
)
from lm_docparse.pdfParser import call_document_parse
from lm_docparse.chunker import to_chunks
'''
LedgerMate — 예산안 PDF 수집(ingest) 스크립트

이 스크립트는 '예산안 PDF 1개'를 입력 받아 아래 과정을 수행한다.

1) (필수) 원문 PDF를 DB의 artifact 테이블에 저장
   - kind="raw_pdf", filename, mime, SHA/크기 등 메타가 저장됨
   - register_artifact() 사용

2) (옵션: --parse) Upstage 문서 파서로 PDF를 파싱하여 JSON 생성 후, JSON도 artifact로 저장
   - lm_docparse.pdfParser.call_document_parse() 호출
   - kind="parse_json" 으로 JSON 아티팩트 저장
   - 이후 청크화 단계(to_chunks)의 입력으로 사용

3) (필수) budget_doc 행 생성
   - 예산 문서의 상위 메타(조직, 제목, 기간, 연결 policy_id, 원본/파싱 artifact id, 작성자)를 기록
   - create_budget_doc() 사용, 반환값은 budget_doc_id(UUID)

4) (옵션: --chunk) 파싱 JSON을 의미 단위(섹션/조항/표)로 청크화하여 budget_chunk 테이블에 일괄 저장
   - lm_docparse.chunker.to_chunks() 로 title/path/code/text/context/tables_json/meta 생성
   - insert_budget_chunks()로 DB 저장
   - policy_id를 함께 넘기면 조항-정책 연결 컬럼이 함께 채워질 수 있음(스키마/함수 구현에 따라 다름)

※ 이 스크립트는 'ETL의 L(Load)'를 책임지는 진입점으로, 
   파서 교체/개선이나 청크화 규칙 변경과 무관하게 DB 저장 계약을 고정하는 것을 목표로 한다.

--------------------------------------------------------------------------------
[필요 환경(로컬 .env)]  (load_dotenv()로 자동 로드)
- DATABASE_URL  : Postgres 접속 DSN (예: postgres://user:pass@127.0.0.1:5432/ledgermate)
- (옵션) UPSTAGE_API_KEY, UPSTAGE_API_BASE : --parse 사용 시 Upstage 인증/엔드포인트
- (옵션) 기타 lm_store/lm_docparse 에서 참조할 환경변수

[주요 의존]
- lm_store.pg: connect, ensure_budget_schema, register_artifact, create_budget_doc, insert_budget_chunks
- lm_docparse.pdfParser: call_document_parse
- lm_docparse.chunker: to_chunks

[CLI 인자]
- pdf (positional)            : 예산안 PDF 경로
- --org-id (required)         : 테넌트/조직 식별자 (예: demo.univ)
- --title                     : 문서 제목(기본값 "예산안")
- --period-from/--period-to   : 문서 적용 기간(YYYY-MM-DD), 스키마에 그대로 저장
- --policy-id                 : 연계할 정책/규정 UUID (선택)
- --created-by                : 작성/업로더 식별자(선택)
- --parse                     : Upstage 파서를 호출해 JSON 생성 및 artifact 저장
- --chunk                     : 파싱 JSON을 청크로 변환하여 budget_chunk 저장
  └ 주의: --chunk만 주고 --parse를 빼면 parsed_obj가 없어 청크화는 스킵됨
          (미리 생성된 parse_json 아티팩트를 읽어들이는 로직이 없다면, --parse를 함께 쓰는 것을 권장)

[실행 예]
python examples/ingest_budget_pdf.py \
  "data/receipts-sample/예산안.pdf" \
  --org-id demo.univ \
  --title "2024 하반기 예산안" \
  --period-from 2024-07-01 --period-to 2024-12-31 \
  --policy-id 66c0efa9-fbe6-446a-9c7e-dd94904926d1 \
  --parse --chunk \
  --created-by yeseul

[출력/부작용]
- 콘솔: 각 단계 artifact/budget_doc/chunk 처리 결과(ID, 건수) 출력
- DB  : artifact(raw_pdf/parse_json) 추가, budget_doc 1행 생성, budget_chunk N행 삽입(옵션)
- 파일: --parse 시 <입력PDF>.parsed.json 임시 파일 생성 후 artifact로 저장

[에러/트러블슈팅]
- Upstage 401 Unauthorized: 결제/크레딧 이슈 또는 API 키 부재 → UPSTAGE_API_KEY/결제상태 확인
- 파일 경로 오류: pdf 인자 경로 확인
- DB 연결 실패: DATABASE_URL 값/네트워크/권한 확인
- --chunk만 실행했는데 0건: parsed_obj가 None → --parse를 함께 사용하거나, 사전 파싱-적재 로직 구현 필요

[설계 노트]
- register_artifact()는 바이트 전체를 읽어 DB/스토리지에 저장하므로 매우 큰 PDF에 대해서는
  스트리밍/청크 업로드로 확장 여지가 있음.
- period-from/to, policy_id, created_by는 budget_doc 메타로 저장되어 이후 검색/필터/추천 연결에 사용됨.
- to_chunks()는 normalize_text() 등 전처리를 포함해 임베딩/검색 품질을 높이는 데 중점.

[실행 방법]

python examples/ingest_budget_pdf.py \
  "data/receipts-sample/예산안.pdf" \
  --org-id demo.univ \
  --title "2024 하반기 예산안" \
  --period-from 2024-07-01 --period-to 2024-12-31 \
  --policy-id <정책UUID> \
  --parse --chunk \
  --out-dir out/receipts \
  --created-by yeseul
'''

# examples/ingest_budget_pdf.py
"""
(요약) 예산안 PDF → (옵션) 파싱 JSON → budget_doc 생성 → (옵션) 청크 생성/DB 저장
- 추가: --out-dir (기본 out/receipts), 파싱/청크 JSON을 파일로도 저장
- 추가: --reuse-parsed: --parse 없이도 기존 parsed JSON이 있으면 재사용
"""

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

    # [NEW] 출력 디렉터리 & 기존 파싱 재사용
    ap.add_argument("--out-dir", default="out/receipts", help="파싱/청크 JSON 저장 디렉터리 (기본: out/receipts)")
    ap.add_argument("--reuse-parsed", action="store_true",
                    help="--parse 미지정이어도 out-dir에 기존 parsed JSON이 있으면 재사용")
    args = ap.parse_args()

    pdf_path = pathlib.Path(args.pdf)
    if not pdf_path.exists():
        raise SystemExit(f"❌ No such file: {pdf_path}")

    out_dir = pathlib.Path(args.out_dir)  # [NEW]
    out_dir.mkdir(parents=True, exist_ok=True)  # [NEW]
    parsed_json_path = out_dir / f"{pdf_path.stem}.parsed.json"  # [NEW]
    chunks_json_path = out_dir / f"{pdf_path.stem}.chunks.json"  # [NEW]

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

        # 2) (옵션) 파싱 JSON artifact + 객체  [개선: 파일도 저장]
        json_art = None
        parsed_obj = None

        # (1) --parse 지정된 경우: API 호출 → parsed.json 저장 → artifact 등록
        if args.parse:
            print(f"→ parsing via Upstage: {pdf_path.name}")
            call_document_parse(str(pdf_path), str(parsed_json_path))  # [NEW] 저장 위치 out/receipts
            jb = parsed_json_path.read_bytes()  # [NEW]
            json_art = register_artifact(
                conn,
                org_id=args.org_id, kind="parse_json",
                filename=parsed_json_path.name, content=jb, mime="application/json"
            )
            print("✔ PARSE artifact:", json_art)
            try:
                parsed_obj = json.loads(jb.decode("utf-8"))
            except Exception as e:
                print("⚠ 파싱 JSON 디코딩 실패:", e)

        # (2) --parse 없지만 --reuse-parsed면: out-dir에서 기존 parsed.json 재사용
        elif args.reuse_parsed and parsed_json_path.exists():  # [NEW]
            print(f"ℹ reuse existing parsed JSON: {parsed_json_path}")
            try:
                jb = parsed_json_path.read_bytes()
                parsed_obj = json.loads(jb.decode("utf-8"))
                # 기존 파일도 artifact로 등록해 두면 추적에 유리
                json_art = register_artifact(
                    conn,
                    org_id=args.org_id, kind="parse_json",
                    filename=parsed_json_path.name, content=jb, mime="application/json"
                )
                print("✔ PARSE artifact (reused):", json_art)
            except Exception as e:
                print("⚠ 기존 parsed JSON 로드 실패:", e)

        # 3) budget_doc 생성
        bid = create_budget_doc(
            conn,
            org_id=args.org_id, title=args.title,
            period_from=args.period_from, period_to=args.period_to,
            policy_id=args.policy_id, source_pdf_id=pdf_art,
            parsed_json_id=json_art, created_by=args.created_by
        )
        print("✅ budget_doc:", bid)

        # 4) (옵션) 청크 생성/저장  [개선: 파일도 저장]
        if args.chunk:
            if parsed_obj is None:
                print("ℹ --chunk 지정됨. parsed_obj가 없어 청크화를 스킵합니다. "
                      "(--parse 또는 --reuse-parsed와 함께 사용 권장)")
            else:
                chunks = to_chunks(parsed_obj)
                # 파일로도 보존
                with chunks_json_path.open("w", encoding="utf-8") as f:  # [NEW]
                    json.dump(chunks, f, ensure_ascii=False, indent=2)
                print(f"🧩 chunks saved: {chunks_json_path} (count={len(chunks)})")  # [NEW]
# 
                # count = insert_budget_chunks(
                #     conn,
                #     budget_doc_id=bid,
                #     org_id=args.org_id,
                #     policy_id=args.policy_id,
                #     chunks=chunks
                # )
                # print(f"🎉 chunks inserted to DB: {count}")

if __name__ == "__main__":
    main()
