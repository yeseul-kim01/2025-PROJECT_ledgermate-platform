from __future__ import annotations
import os, json, psycopg2
from pathlib import Path
from lm_rag.embeddings_upstage import embed_texts
from dotenv import load_dotenv


_DSN = os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/ledgermate"

def _pg():
    return psycopg2.connect(_DSN)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="budgets/.../artifacts/*.json")  # ← dest 사용
    args = ap.parse_args()

    data = json.loads(Path(args.in_path).read_text(encoding="utf-8"))  # ← args.in_path 로 변경
    rows = data if isinstance(data, list) else data.get("lines", [])

    texts = [f"{r.get('line_title','')} {r.get('category_path','')} {r.get('line_code','')}".strip() for r in rows]
    embs = embed_texts(texts)

    sql = "INSERT INTO budget_lines (line_title,line_code,category_path,remaining_amount,embedding) VALUES (%s,%s,%s,%s,%s)"
    with _pg() as conn, conn.cursor() as cur:
        for r, e in zip(rows, embs):
            cur.execute(sql, (r.get('line_title'), r.get('line_code'), r.get('category_path'),
                              r.get('remaining_amount'), e))
    print(f"[OK] inserted {len(rows)} budget lines")

if __name__ == "__main__":
    main()
