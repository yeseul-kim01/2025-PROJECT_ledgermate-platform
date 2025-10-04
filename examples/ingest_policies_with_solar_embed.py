from __future__ import annotations
import os, json, psycopg2
from pathlib import Path
from typing import List, Dict, Any
from lm_rag.embeddings_upstage import embed_texts
from dotenv import load_dotenv

_DSN = os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/ledgermate"

def _pg():
    return psycopg2.connect(_DSN)

def load_policy_chunks(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("chunks", [])

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="out/policies/...chunks.json")  # ← dest 사용
    args = ap.parse_args()

    chunks = load_policy_chunks(Path(args.in_path))  # ← args.in_path 로 변경
    texts = [c.get("snippet","") for c in chunks]
    embs = embed_texts(texts)

    sql = "INSERT INTO policy_chunks (doc_title,version,section,page,snippet,embedding) VALUES (%s,%s,%s,%s,%s,%s)"
    with _pg() as conn, conn.cursor() as cur:
        for c, e in zip(chunks, embs):
            cur.execute(sql, (c.get("doc_title"), c.get("version"), c.get("section"),
                              c.get("page"), c.get("snippet"), e))
    print(f"[OK] inserted {len(chunks)} policy chunks")

if __name__ == "__main__":
    main()
