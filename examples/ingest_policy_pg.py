# examples/ingest_policy_pg.py
"""
LedgerMate — ingest_policy_pg.py (policy only / no rule_chunk)

- *.chunks.jsonl 또는 *.chunks.json 입력 지원
- source_pdf 없으면 입력 파일 자체 스트리밍 해시
- (선택) meta.json 있으면 거기서 version 자동 추론; --version이 있으면 그 값을 우선
"""

from __future__ import annotations
import os, sys, json, hashlib, pathlib, argparse
from dotenv import load_dotenv
from typing import Optional
from lm_store.pg import connect, ensure_schema, upsert_policy

load_dotenv()

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def detect_format(p: pathlib.Path) -> str:
    s = p.suffix.lower()
    if s == ".jsonl": return "jsonl"
    if s == ".json":  return "json"
    # fallback: 첫 줄로 판별
    try:
        head = p.read_text(encoding="utf-8").lstrip()[:1]
        return "json" if head == "[" or head == "{" else "jsonl"
    except Exception:
        return "jsonl"

def load_first_chunk(chunks_path: str) -> Optional[dict]:
    p = pathlib.Path(chunks_path)
    kind = detect_format(p)
    if kind == "jsonl":
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try: return json.loads(line)
                    except Exception: return None
        return None
    else:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(obj, list) and obj: return obj[0]
        if isinstance(obj, dict): return obj
        return None

def load_meta_if_exists(chunks_path: str) -> dict:
    p = pathlib.Path(chunks_path)
    stem = p.stem.replace(".chunks", "")  # *.chunks.json → stem 보정
    # 같은 폴더
    meta_path = p.with_name(f"{stem}.meta.json")
    if meta_path.exists():
        try: return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception: pass
    # 전형적인 out/chunks 위치
    alt = pathlib.Path("out/chunks") / f"{stem}.meta.json"
    if alt.exists():
        try: return json.loads(alt.read_text(encoding="utf-8"))
        except Exception: pass
    return {}

def coalesce_version(cli_version: Optional[str], first_chunk: Optional[dict], meta: dict, fallback: str) -> str:
    if cli_version: return cli_version
    mv = meta.get("version") or {}
    eff = mv.get("effective_date") or mv.get("effective")
    prg = mv.get("promulgation_no") or mv.get("promulgation")
    if eff or prg: return f"{eff or ''}/{prg or ''}".strip("/")
    if first_chunk and isinstance(first_chunk.get("version"), dict):
        v = first_chunk["version"]; eff=v.get("effective_date"); prg=v.get("promulgation_no")
        if eff or prg: return f"{eff or ''}/{prg or ''}".strip("/")
    return fallback  # 파일명 등

def main(chunks_path: str, org_id: str, version_opt: Optional[str], source_pdf: Optional[str]):
    p = pathlib.Path(chunks_path)
    if not p.exists():
        print(f"❌ no such file: {chunks_path}", file=sys.stderr); sys.exit(1)

    # 청크/메타 일부만 살짝 읽어 메타 정보 추출
    first = load_first_chunk(chunks_path)
    meta  = load_meta_if_exists(chunks_path)

    # 원본 해시: PDF 우선, 없으면 입력 파일 자체( json/jsonl 상관없이 스트리밍 해시 )
    if source_pdf:
        sha = file_sha256(source_pdf)
        source_name = pathlib.Path(source_pdf).name
    else:
        sha = file_sha256(chunks_path)
        source_name = p.name

    # DB 연결
    conn = connect()
    # ensure_schema(conn)  # 최초 1회만 풀기

    # RLS org 설정
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.org_id', %s, true)", (org_id,))
    conn.commit()

    # 버전 문자열 합치기
    version = coalesce_version(version_opt, first, meta, fallback=p.stem)

    # (선택) policy.extra_meta에 유용한 것 저장
    extra_meta = {
        "chunks_kind": detect_format(p),
        "source_name": source_name,
        "version": meta.get("version") or (first.get("version") if first else None),
        "adapter_seed": meta.get("adapter_seed"),  # 있으면 downstream에 도움
    }

    policy_id = upsert_policy(
        conn,
        org_id=org_id,
        version=version,
        source_name=source_name,
        sha256=sha,
    )

    print(f"✅ policy_id={policy_id} org_id={org_id} version={version} source_name={source_name} sha256={sha[:12]}...")
    print("ℹ️ rule_chunk INSERT는 스킵했습니다. (추후 별도 스크립트에서 적재)")
    if extra_meta.get("adapter_seed"):
        print("🔎 adapter_seed present in meta")

    conn.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks", help="*.chunks.jsonl 또는 *.chunks.json 경로")
    ap.add_argument("--org-id", default=os.getenv("ORG_ID", "demo.univ"))
    ap.add_argument("--version", default=None, help="미지정 시 meta/청크에서 자동 추론")
    ap.add_argument("--source-pdf", default=None)
    args = ap.parse_args()
    main(args.chunks, args.org_id, args.version, args.source_pdf)
