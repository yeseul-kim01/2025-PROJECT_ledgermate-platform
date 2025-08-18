# examples/ingest_policy_pg.py
from __future__ import annotations
import os, sys, json, hashlib, pathlib, argparse
from dotenv import load_dotenv
from lm_store.pg import connect, ensure_schema, upsert_policy, bulk_insert_chunks, sha256_json

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def main(chunks_path: str, org_id: str, version: str, source_pdf: str | None):
    # 1) 청크 로드
    chunks = json.load(open(chunks_path, encoding="utf-8"))

    # 2) 원본 식별값
    if source_pdf:
        sha = file_sha256(source_pdf)
        source_name = pathlib.Path(source_pdf).name
    else:
        sha = sha256_json(chunks)  # pdf가 없으면 JSON 자체 해시로라도 중복 방지
        source_name = pathlib.Path(chunks_path).name

    # 3) DB 연결 + (최초 1회) 스키마 보장
    conn = connect()
    # ensure_schema(conn)  # 스키마 처음 만들 때만 주석 해제

    # 4) RLS 통과용 테넌트 지정
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.org_id', %s, true)", (org_id,))
    conn.commit()

    # 5) policy upsert + 청크 벌크 저장
    policy_id = upsert_policy(
        conn,
        org_id=org_id,
        version=version,
        source_name=source_name,
        sha256=sha,
    )
    n = bulk_insert_chunks(conn, policy_id, org_id, chunks)

    print(f"✅ policy_id={policy_id} inserted_chunks={n} org_id={org_id} version={version}")

if __name__ == "__main__":
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks", help="*.chunks.json 경로")
    ap.add_argument("--org-id", default=os.getenv("ORG_ID", "demo.univ"))
    ap.add_argument("--version", required=True)
    ap.add_argument("--source-pdf", default=None)
    args = ap.parse_args()
    main(args.chunks, args.org_id, args.version, args.source_pdf)
