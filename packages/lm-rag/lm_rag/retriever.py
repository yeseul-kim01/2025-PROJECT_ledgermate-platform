# packages/lm-rag/lm_rag/retriever.py
from __future__ import annotations
import os, psycopg2
from typing import Any, Dict, List
from .embeddings_upstage import embed_texts

_DSN = os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/ledgermate"
_EMB_DIM = int(os.getenv("RAG_EMB_DIM", "4096"))  # 테이블 vector 차원과 일치해야 함!

def _pg():
    return psycopg2.connect(_DSN)

def _pick_col(cols: set[str], *candidates: str) -> str | None:
    for c in candidates:
        if c in cols:
            return c
    return None

def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

def _table_columns(conn, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
        """, (table,))
        return {r[0] for r in cur.fetchall()}

def _zero_vec(n: int = _EMB_DIM) -> List[float]:
    return [0.0] * n

class RAG:
    def __init__(self, k_rules: int = 6, k_budgets: int = 5, org_id: str | None = None):
        self.k_rules = k_rules
        self.k_budgets = k_budgets
        self.org_id = org_id

    def _embed(self, q: str) -> List[float]:
        q = (q or "").strip()
        if not q:
            return _zero_vec()
        try:
            vecs = embed_texts([q])
            if not vecs or not vecs[0]:
                return _zero_vec()
            return vecs[0]
        except Exception:
            return _zero_vec()

    def search_rules(self, query_text: str) -> List[Dict[str, Any]]:
        qe = self._embed(query_text)               # ← 빈문자열도 안전
        qv = _vec_literal(qe)
        with _pg() as conn, conn.cursor() as cur:
            rc_cols = _table_columns(conn, "rule_chunk")
            p_cols  = _table_columns(conn, "policy")
            section_col = "section" if "section" in rc_cols else ("heading" if "heading" in rc_cols else None)
            page_col    = "page"    if "page" in rc_cols    else ("page_no" if "page_no" in rc_cols else None)
            snippet_col = "snippet" if "snippet" in rc_cols else ("text" if "text" in rc_cols else None)
            section_sel = section_col if section_col else "NULL::text AS section"
            page_sel    = page_col    if page_col    else "NULL::int  AS page"
            snippet_sel = snippet_col if snippet_col else "NULL::text AS snippet"

            where_clause = ""
            params: list[Any] = [qv]
            if self.org_id:
                if "org_id" in rc_cols:
                    where_clause = "WHERE rc.org_id = %s"
                elif "org_id" in p_cols:
                    where_clause = "WHERE p.org_id = %s"
                if where_clause:
                    params.append(self.org_id)
            params += [qv, self.k_rules]

            sql = f"""
                SELECT
                    COALESCE(p.source_name, '재정운용세칙') AS doc,
                    p.version,
                    {section_sel},
                    {page_sel},
                    {snippet_sel},
                    1 - (rc.embedding <=> %s::vector) AS score
                FROM rule_chunk rc
                JOIN policy p ON p.id = rc.policy_id
                {where_clause}
                ORDER BY rc.embedding <=> %s::vector
                LIMIT %s;
            """
            probes = os.getenv("PGVECTOR_PROBES")
            if probes:
                cur.execute(f"SET ivfflat.probes = {int(probes)};")
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

        return [{
            "doc": r[0],
            "version": r[1],
            "section": r[2],
            "page": r[3],
            "snippet": r[4],
            "score": float(r[5]) if r[5] is not None else None
        } for r in rows]

    def search_budget_lines(self, category_hint: str | None = None, query_text: str | None = None) -> List[Dict[str, Any]]:
        seed = (query_text or category_hint or "").strip()
        qe = self._embed(seed)                      # ← seed가 비어도 안전
        use_small = os.getenv("RAG_BUDGET_EMB", "").lower() in ("i2000", "small", "2000")
        emb_vec = qe[:2000] if use_small else qe
        emb_col = "embedding_i2000" if use_small else "embedding"
        qv = _vec_literal(emb_vec)

        with _pg() as conn, conn.cursor() as cur:
            bl_cols = _table_columns(conn, "budget_line")
            bd_cols = _table_columns(conn, "budget_doc")

            if emb_col not in bl_cols:
                if "embedding" in bl_cols:
                    emb_col = "embedding"; qv = _vec_literal(qe)
                elif "embedding_i2000" in bl_cols:
                    emb_col = "embedding_i2000"; qv = _vec_literal(qe[:2000])
                else:
                    raise RuntimeError("budget_line has no embedding/embedding_i2000 column")

            # 선택 컬럼들
            code_col     = _pick_col(bl_cols, "code")
            category_col = _pick_col(bl_cols, "category")
            subcat_col   = _pick_col(bl_cols, "subcat")
            item_col     = _pick_col(bl_cols, "item")
            title_col    = _pick_col(bl_cols, "title", "line_title", "name")  # ← 추가
            amount_col   = _pick_col(bl_cols, "amount")

            # 코드 유효성 (DB code가 3자리/3-3/3-3-3면 사용)
            valid_pat = r"^[0-9]{3}(?:-[0-9]{3}(?:-[0-9]{3})?)?$"
            code_valid = f"CASE WHEN {code_col} ~ '{valid_pat}' THEN {code_col} ELSE NULL END" if code_col else "NULL::text"

            # 코드 텍스트 추출: item/category/subcat/title에서 3자리(또는 3-3(-3))을 찾음
            blob_parts = [c for c in (item_col, category_col, subcat_col, title_col) if c]
            blob = " || ' ' || ".join(blob_parts) if blob_parts else "''"
            code_from_text = f"(regexp_match({blob}, '(\\d{{3}}(?:-\\d{{3}}(?:-\\d{{3}})?)?)'))[1]"

            # 최종 code 선택
            code_sel = f"COALESCE({code_valid}, {code_from_text}, NULL::text) AS line_code"

            if category_col and subcat_col:
                category_sel = f"({category_col} || '>' || {subcat_col}) AS category_path"
            elif category_col:
                category_sel = f"{category_col} AS category_path"
            else:
                category_sel = "NULL::text AS category_path"

            title_sel     = (item_col    or "NULL::text")    + " AS line_title"
            remaining_sel = (amount_col  or "NULL::numeric") + " AS remaining_amount"

            where_clause = ""
            params: list[Any] = [qv]
            if self.org_id and ("org_id" in bd_cols):
                where_clause = "WHERE bd.org_id = %s"
                params.append(self.org_id)
            params += [qv, self.k_budgets]

            sql = f"""
                SELECT
                    {title_sel},
                    {code_sel},
                    {category_sel},
                    {remaining_sel},
                    1 - (bl.{emb_col} <=> %s::vector) AS score
                FROM budget_line bl
                JOIN budget_doc bd ON bd.id = bl.budget_id
                {where_clause}
                ORDER BY bl.{emb_col} <=> %s::vector
                LIMIT %s;
            """

            probes = os.getenv("PGVECTOR_PROBES")
            if probes:
                cur.execute(f"SET ivfflat.probes = {int(probes)};")
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

        return [{
            "line_title": r[0],
            "line_code": r[1],
            "category_path": r[2],
            "remaining_amount": float(r[3]) if r[3] is not None else None,
            "score": float(r[4]) if r[4] is not None else None
        } for r in rows]
