# bin/ingest_budget_lines.py
from __future__ import annotations
import os, json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# 4096 임베딩 + 2000 축소
from lm_rag.embeddings_upstage import embed_texts, reduce_embeddings

load_dotenv()

_DSN = os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/ledgermate"


def _pg():
    return psycopg2.connect(_DSN)


def _load_rows(p: Path) -> List[Dict[str, Any]]:
    """
    입력 JSON이 배열이거나, lines/chunks/items/rows/data 중 하나에 배열로 들어오는 경우 모두 수용
    """
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    for key in ("lines", "chunks", "items", "rows", "data"):
        v = data.get(key)
        if isinstance(v, list):
            return v
    return []


def _split_category(path: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """'운영비>소모품비>문구' → ('운영비','소모품비')"""
    if not path:
        return None, None
    parts = [s.strip() for s in str(path).split(">") if s and s.strip()]
    cat = parts[0] if len(parts) >= 1 else None
    sub = parts[1] if len(parts) >= 2 else None
    return cat, sub


def _val(d: Dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return str(v)
    return default


def _build_texts(rows: List[Dict[str, Any]]) -> List[str]:
    """
    임베딩 입력 텍스트 빌드:
    - lines 모드: line_title + category_path + line_code (+ notes)
    - chunks 모드: title + text(최대 300자) + code + path/section_path
    - 그 외: title/name/item/desc 섞어서 최대한 채움
    """
    texts: List[str] = []
    if not rows:
        return texts

    # 모드 감지
    is_lines = any(set(r.keys()) & {"line_title", "line_code", "category_path"} for r in rows)

    for r in rows:
        if is_lines:
            s = " ".join(
                x for x in (
                    _val(r, "line_title", "title", "item"),
                    _val(r, "category_path", "category"),
                    _val(r, "line_code", "code"),
                    _val(r, "notes", "desc"),
                ) if x
            ).strip()
        else:
            # chunks or others
            s = " ".join(
                x for x in (
                    _val(r, "title", "line_title", "item", "name"),
                    _val(r, "text")[:300],
                    _val(r, "code", "line_code", "id"),
                    _val(r, "path", "section_path", "category_path"),
                ) if x
            ).strip()
        texts.append(s or " ")  # 완전 빈 문자열 방지
    return texts


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help=".../*.json (lines or chunks)")
    ap.add_argument("--budget-id", required=True, help="budget_doc.id (UUID)")
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--base-url", default=None)
    args = ap.parse_args()

    rows = _load_rows(Path(args.in_path))
    print(f"[DEBUG] rows={len(rows)}")
    if not rows:
        print("[WARN] no rows in input; nothing to insert")
        return

    texts = _build_texts(rows)
    nonempty = sum(1 for t in texts if t and t.strip())
    print(f"[DEBUG] texts_nonempty={nonempty} sample={texts[:2]}")
    if nonempty == 0:
        print("[ERROR] All texts empty. Check JSON keys or file schema.")
        return

    # 1) 임베딩 생성 (4096 → 2000)
    embs_4096 = embed_texts(texts, api_key=args.api_key, base_url=args.base_url)
    print(f"[DEBUG] embs_len={len(embs_4096)}")
    if not embs_4096:
        print("[ERROR] Embedding API returned empty. Verify --api-key/--base-url (or UPSTAGE_* env).")
        return
    dim_in = len(embs_4096[0])
    embs_2000 = reduce_embeddings(embs_4096, dim_out=2000, assume_dim_in=dim_in)

    # 2) records 구성 (lines/chunks 자동 감지)
    is_lines = any(set(rows[0].keys()) & {"line_title", "line_code", "category_path"}) if rows else False
    sql = """
    INSERT INTO budget_line
      (budget_id, line_no, code, category, subcat, item, amount, currency, notes, embedding, embedding_i2000)
    VALUES (%(budget_id)s, %(line_no)s, %(code)s, %(category)s, %(subcat)s, %(item)s,
            %(amount)s, %(currency)s, %(notes)s, %(embedding)s, %(embedding_i2000)s)
    """

    records: List[Dict[str, Any]] = []
    for idx, (r, e4096, e2000) in enumerate(zip(rows, embs_4096, embs_2000), start=1):
        if is_lines:
            category, subcat = _split_category(r.get("category_path"))
            amount = r.get("remaining_amount")
            if amount in (None, ""):
                amount = r.get("amount")
            try:
                amount = None if amount in (None, "") else float(amount)
            except Exception:
                amount = None

            rec = {
                "budget_id": args.budget_id,
                "line_no": idx,
                "code": r.get("line_code"),
                "category": category,
                "subcat": subcat,
                "item": r.get("line_title"),
                "amount": amount,
                "currency": "KRW",
                "notes": r.get("notes"),
                "embedding": e4096,
                "embedding_i2000": e2000,
            }
        else:
            # chunks → 최소 매핑
            rec = {
                "budget_id": args.budget_id,
                "line_no": idx,
                "code": _val(r, "code", "line_code", "id") or None,
                "category": None,
                "subcat": None,
                "item": _val(r, "title", "line_title", "item", "name") or None,
                "amount": None,
                "currency": "KRW",
                "notes": _val(r, "path", "section_path", "category_path") or None,
                "embedding": e4096,
                "embedding_i2000": e2000,
            }
        records.append(rec)

    # 3) 대량 삽입
    with _pg() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, records, page_size=500)

    print(f"[OK] inserted {len(records)} budget lines into budget_line (budget_id={args.budget_id})")


if __name__ == "__main__":
    main()
