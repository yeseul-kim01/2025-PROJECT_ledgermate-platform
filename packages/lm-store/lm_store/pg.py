# packages/lm-store/lm_store/pg.py
from __future__ import annotations
import hashlib, json, os, pathlib
from typing import Iterable, Dict, Any, Optional
import psycopg
from psycopg.rows import dict_row


SCHEMA_SQL_PATH = pathlib.Path(__file__).with_name("pg_schema.sql")
_env_budget = os.getenv("LM_BUDGET_SCHEMA")
if _env_budget:
    SCHEMA_SQL_BUDGET_PATH = pathlib.Path(_env_budget).expanduser().resolve()
else:
    SCHEMA_SQL_BUDGET_PATH = pathlib.Path(__file__).with_name("pg_schema_budget.sql")
STORAGE_DIR = pathlib.Path(os.getenv("STORAGE_DIR", "storage")).resolve()

def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

def register_artifact(conn: psycopg.Connection, *, org_id: str, kind: str,
                      filename: str, content: bytes, mime: Optional[str] = None) -> str:
    """파일을 로컬 디스크에 저장하고 artifact 레코드 생성/재사용."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    sha = _sha256_bytes(content)
    mime = mime or (mimetypes.guess_type(filename)[0] or "application/octet-stream")
    size = len(content)

    with conn.cursor() as cur:
        # 이미 있으면 재사용
        cur.execute("""
          SELECT id, storage_path FROM artifact
           WHERE org_id=%(org)s AND sha256=%(sha)s AND kind=%(k)s
          """, dict(org=org_id, sha=sha, k=kind))
        row = cur.fetchone()
        if row:
            return row["id"]

        # 새로 만들 id를 먼저 받아옴
        cur.execute("""
          INSERT INTO artifact (org_id, kind, filename, mime, size_bytes, sha256, storage_path)
          VALUES (%(org)s,%(k)s,%(fn)s,%(mime)s,%(sz)s,%(sha)s,'')
          RETURNING id
        """, dict(org=org_id, k=kind, fn=filename, mime=mime, sz=size, sha=sha))
        art_id = row_id = cur.fetchone()["id"]

        # 파일 저장 (org_id/아티팩트ID.확장자)
        ext = pathlib.Path(filename).suffix or ".bin"
        rel = pathlib.Path(org_id) / "artifacts" / f"{art_id}{ext}"
        abs_path = STORAGE_DIR / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(content)

        # 경로 업데이트
        cur.execute("UPDATE artifact SET storage_path=%s WHERE id=%s", (str(rel), art_id))
    conn.commit()
    return art_id

def create_budget_doc(conn: psycopg.Connection, *, org_id: str, title: str,
                      source_pdf_id: str, period_from=None, period_to=None,
                      policy_id: Optional[str] = None, parsed_json_id: Optional[str] = None,
                      created_by: Optional[str] = None) -> str:
    with conn.cursor() as cur:
        cur.execute("""
          INSERT INTO budget_doc (org_id, title, period_from, period_to, policy_id,
                                  source_pdf, parsed_json, created_by)
          VALUES (%(org)s,%(title)s,%(pf)s,%(pt)s,%(pid)s,%(pdf)s,%(json)s,%(by)s)
          RETURNING id
        """, dict(org=org_id, title=title, pf=period_from, pt=period_to,
                  pid=policy_id, pdf=source_pdf_id, json=parsed_json_id, by=created_by))
        bid = cur.fetchone()["id"]
    conn.commit()
    return bid

def connect() -> psycopg.Connection:
    dsn = os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/ledgermate"
    return psycopg.connect(dsn, row_factory=dict_row)

def ensure_schema(conn: psycopg.Connection):
    sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    
def ensure_budget_schema(conn: psycopg.Connection):
    sql = SCHEMA_SQL_BUDGET_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

def sha256_json(obj: Any) -> str:
    # Upstage 파서 RAW JSON도 중복 체크 가능
    b = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return sha256_bytes(b)

def upsert_policy(conn: psycopg.Connection, *, org_id: str, version: str,
                  source_name: str, sha256: str,
                  effective_from: Optional[str] = None,
                  effective_to: Optional[str] = None,
                  supersedes_id: Optional[str] = None) -> str:
    sql = """
    INSERT INTO policy (org_id, version, source_name, sha256, effective_from, effective_to, supersedes_id)
    VALUES (%(org_id)s, %(version)s, %(source_name)s, %(sha256)s, %(ef)s, %(et)s, %(sup)s)
    ON CONFLICT (org_id, sha256)
      DO UPDATE SET version = EXCLUDED.version
    RETURNING id;
    """
    with conn.cursor() as cur:
        cur.execute(sql, dict(org_id=org_id, version=version, source_name=source_name,
                              sha256=sha256, ef=effective_from, et=effective_to, sup=supersedes_id))
        pid = cur.fetchone()["id"]
    conn.commit()
    return pid

def bulk_insert_chunks(conn: psycopg.Connection, policy_id: str, org_id: str,
                       chunks: Iterable[Dict[str, Any]]):
    rows = []
    for ch in chunks:
        rows.append((
            policy_id, org_id,
            int(ch.get("order", 0)),
            ch.get("code"), ch.get("title"), ch.get("path"),
            ch.get("text") or "", ch.get("context_text"),
            json.dumps(ch.get("tables"), ensure_ascii=False) if "tables" in ch else None
        ))
    if not rows:
        return 0
    sql = """
    INSERT INTO rule_chunk
      (policy_id, org_id, ord, code, title, path, text, context_text, tables_json)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)
