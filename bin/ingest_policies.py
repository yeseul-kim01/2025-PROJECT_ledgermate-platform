# bin/ingest_policies.py
from __future__ import annotations

import os, json, hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

import psycopg2
from dotenv import load_dotenv
from lm_rag.embeddings_upstage import embed_texts, reduce_embeddings

load_dotenv()

ORG_ID = os.getenv("LM_ORG_ID", "demo.univ")
_DSN   = os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/ledgermate"

def _pg():
    return psycopg2.connect(_DSN)

def _detect_format(p: Path) -> str:
    s = p.suffix.lower()
    if s == ".jsonl": return "jsonl"
    if s == ".json":  return "json"
    # fallback: 첫 글자 판별
    head = p.read_text(encoding="utf-8").lstrip()[:1]
    return "json" if head in "[{" else "jsonl"

def load_policy_chunks(path: Path) -> List[Dict[str, Any]]:
    kind = _detect_format(path)
    if kind == "jsonl":
        out: List[Dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln: 
                    continue
                out.append(json.loads(ln))
        return out
    else:
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
    ap.add_argument("--in", dest="in_path", required=True, help="out/chunks/*.chunks.jsonl|json")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--policy-id", default=None, help="미지정 시 자동 upsert 후 생성")
    args = ap.parse_args()

    in_path   = Path(args.in_path)
    chunks    = load_policy_chunks(in_path)
    if not chunks:
        raise SystemExit("❌ no chunks found")

    # 파일 단위 식별자 (원본 파일명/sha)
    source_name = in_path.name
    file_sha    = hashlib.sha256(in_path.read_bytes()).hexdigest()

    # 버전 (청크에 version dict가 있으면 date/번호로, 없으면 v1)
    v = chunks[0].get("version") if isinstance(chunks[0], dict) else None
    if isinstance(v, dict):
        eff = v.get("effective_date") or ""
        prg = v.get("promulgation_no") or ""
        version = (f"{eff}/{prg}".strip("/")) or "v1"
    else:
        version = v or "v1"

    # policy_id 확보(넘겨주지 않으면 자동 생성/업서트)
    policy_id = args.policy_id
    if not policy_id:
        with _pg() as conn:
            policy_id = upsert_policy(conn, ORG_ID, source_name, version, file_sha)
    # 문자열 캐스팅 방지(정수/UUID 그대로 쓰기)
    print(f"policy_id={policy_id}")

    # 텍스트/메타 준비
    texts: List[str] = []
    pairs: List[tuple[int, Dict[str, Any], str]] = []
    for i, c in enumerate(chunks, 1):  # ord=i
        s = (c.get("text") or "").strip()
        if not s: 
            continue
        pairs.append((i, c, s))
        texts.append(s)

    if not texts:
        raise SystemExit("❌ chunks have no text")

    # 임베딩 생성
    embs_4096 = embed_texts(texts, api_key=args.api_key, base_url=args.base_url)
    dim_in    = len(embs_4096[0]) if embs_4096 else 0
    embs_i2000= reduce_embeddings(embs_4096, dim_out=2000, assume_dim_in=dim_in)

    insert_sql = """
    INSERT INTO rule_chunk
      (policy_id, org_id, ord, code, title, path, text, context_text, tables_json, embedding, embedding_i2000)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """

    with _pg() as conn:
        with conn.cursor() as cur:
            for (ord_no, c, s), e4096, e2000 in zip(pairs, embs_4096, embs_i2000):
                code   = c.get("code")
                title  = c.get("title") or c.get("doc_title") or c.get("section")
                path   = c.get("path")  or c.get("section")
                ctxt   = c.get("context_text")  # 있으면 저장
                tables = c.get("tables") or c.get("tables_json")
                tables_json = json.dumps(tables, ensure_ascii=False) if tables else None

                cur.execute(
                    insert_sql,
                    (
                        policy_id,
                        ORG_ID,
                        ord_no,
                        code,
                        title,
                        path,
                        s,
                        ctxt,
                        tables_json,
                        e4096,
                        e2000,
                    ),
                )

    print(f"[OK] inserted {len(embs_4096)} rule chunks (policy_id={policy_id})")

if __name__ == "__main__":
    main()
