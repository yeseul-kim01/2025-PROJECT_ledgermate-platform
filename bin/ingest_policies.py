# bin/ingest_policies.py
from __future__ import annotations

import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# 패키지 임포트 (lm-rag)
from lm_rag.embeddings_upstage import embed_texts, reduce_embeddings

load_dotenv()

ORG_ID = os.getenv("LM_ORG_ID", "demo.univ")
_DSN = os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/ledgermate"


def _pg():
    return psycopg2.connect(_DSN)


def load_policy_chunks(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("chunks", [])


def upsert_policy(conn, org_id, source_name, version, file_sha) -> str:
    sql = """
    INSERT INTO policy (org_id, version, source_name, sha256)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (org_id, sha256) DO UPDATE SET version = EXCLUDED.version
    RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (org_id, version, source_name, file_sha))
        return cur.fetchone()[0]


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="out/policies/...chunks.json")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default=None)
    args = ap.parse_args()

    chunks = load_policy_chunks(Path(args.in_path))

    # 파일 단위 식별자 (원본 파일명/sha)
    source_name = Path(args.in_path).name
    file_sha = hashlib.sha256(Path(args.in_path).read_bytes()).hexdigest()
    version = (chunks[0].get("version") if chunks else None) or "v1"

    # 텍스트/메타 준비
    texts: List[str] = []
    pairs: List[tuple[int, Dict[str, Any], str]] = []
    for i, c in enumerate(chunks, 1):
        s = (c.get("text") or "").strip()
        if not s:
            continue
        pairs.append((i, c, s))  # ord=i 보존
        texts.append(s)

    # 임베딩 생성 (원본 4096 가정, 모델에 따라 달라도 reduce_embeddings가 방어)
    embs_4096 = embed_texts(texts, api_key=args.api_key, base_url=args.base_url)
    dim_in = len(embs_4096[0]) if embs_4096 else 0
    embs_i2000 = reduce_embeddings(embs_4096, dim_out=2000, assume_dim_in=dim_in)

    with _pg() as conn:
        policy_id = upsert_policy(conn, ORG_ID, source_name, version, file_sha)

        sql = """
        INSERT INTO rule_chunk
          (policy_id, org_id, ord, code, title, path, text, context_text, tables_json, embedding, embedding_i2000)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        with conn.cursor() as cur:
            for (ord_no, c, s), e4096, e2000 in zip(pairs, embs_4096, embs_i2000):
                cur.execute(
                    sql,
                    (
                        policy_id,
                        ORG_ID,
                        ord_no,
                        c.get("code"),
                        c.get("doc_title") or c.get("title") or c.get("section"),
                        c.get("section"),
                        s,
                        None,
                        None,
                        e4096,  # 4096 원본
                        e2000,  # 2000 축소본 (HNSW 인덱싱용)
                    ),
                )

    print(f"[OK] inserted {len(embs_4096)} rule chunks (policy_id={policy_id})")


if __name__ == "__main__":
    main()
