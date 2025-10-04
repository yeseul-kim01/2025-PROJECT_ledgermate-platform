# examples/quick_search.py
from __future__ import annotations
import os
import sys
import json
import psycopg2
from dotenv import load_dotenv

# 4096 임베딩 + 2000 축소 유틸
from lm_rag.embeddings_upstage import embed_texts, reduce_embeddings

load_dotenv()

QUERY = sys.argv[1] if len(sys.argv) > 1 else "간담회 다과비 처리 기준"
TOPK = int(os.getenv("TOPK", 10))

# ORG
ORG_ID = os.getenv("LM_ORG_ID", "demo.univ")

# DSN
DSN = (
    os.getenv("POSTGRES_DSN")
    or os.getenv("PG_DSN")
    or "postgresql://postgres:postgres@localhost:5432/ledgermate"
)

# Upstage API 설정
UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
UPSTAGE_BASE_URL = os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1")


def _vec_str(v, dims: int) -> str:
    """pgvector 문자열 리터럴: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{float(x):.8f}" for x in v[:dims]) + "]"


def main():
    # 1) 쿼리 임베딩 생성 (4096) → 2000으로 축소
    q4096 = embed_texts([QUERY], api_key=UPSTAGE_API_KEY, base_url=UPSTAGE_BASE_URL)
    if not q4096:
        print("[ERROR] embedding failed (check UPSTAGE_API_KEY / UPSTAGE_BASE_URL)")
        sys.exit(1)
    q2000 = reduce_embeddings(q4096, dim_out=2000)[0]
    q2000_str = _vec_str(q2000, 2000)

    # 2) DB 접속
    with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
        # RLS 사용 시 org_id 세션 설정
        try:
            cur.execute("SET app.org_id = %s", (ORG_ID,))
        except Exception:
            # 정책/청크에만 RLS 켜진 상태면 다른 테이블에서는 없어도 OK
            pass

        # 3) 검색 (rule_chunk)
        sql = """
        WITH q AS (SELECT %s::vector(2000) AS v)
        SELECT
          id,
          ord,
          title,
          LEFT(text, 160) AS preview,
          (embedding_i2000 <=> (SELECT v FROM q)) AS dist
        FROM rule_chunk
        WHERE org_id = %s
        ORDER BY embedding_i2000 <=> (SELECT v FROM q)
        LIMIT %s;
        """

        cur.execute(sql, (q2000_str, ORG_ID, TOPK))
        rows = cur.fetchall()

    # 4) 출력
    # rows: [(id, ord, title, preview, dist), ...]
    out = [
        {
            "id": r[0],
            "ord": r[1],
            "title": r[2],
            "preview": r[3],
            "distance": float(r[4]),
        }
        for r in rows
    ]
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
