#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
자연어 → 템플릿 표준 형식 JSON (예산안 한 행)
- DB(rule_chunk/rule_embedding)에서 세칙 Top-K를 뽑아 LLM 프롬프트에 주입
- pgvector 있으면 임베딩 유사도, 없으면 LIKE 폴백
"""
import os, sys, json, math
from pathlib import Path
from argparse import ArgumentParser
from dotenv import load_dotenv
from openai import OpenAI

# ---- repo/out 경로 ----
def find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / "packages").exists() or (p / "pyproject.toml").exists():
            return p
    return cur

SCRIPT_PATH = Path(__file__).resolve()
ROOT = find_repo_root(SCRIPT_PATH.parent)
OUT_DIR = ROOT / "out"
PROFILE_PATH = OUT_DIR / "budget_profile.json"
RESULT_PATH = OUT_DIR / "compose_result.json"

SCHEMA_HINT = {
    "section": "expense_details",
    "subgroup": "<텍스트 또는 null>",
    "item": "<비목명>",
    "description": "<세부내역 자연어>",
    "formula": {"unit_price": "int", "quantity": "int", "times": "int"},
    "amount_expected": "int",
    "reason": "<편성 사유>",
    "evidence": [{"ord": "int", "path": "string", "quote": "string"}],
    "warnings": ["string"]
}

def strip_json(text: str) -> str:
    s = text.strip()
    b = s.find("{"); e = s.rfind("}")
    if b == -1 or e == -1 or e <= b:
        raise ValueError("응답에서 JSON 블록을 찾지 못했습니다.")
    return s[b:e+1]

def cint(x):
    try:
        if x is None: return None
        if isinstance(x, (int, float)): return int(round(x))
        return int(float(str(x).replace(",", "").strip()))
    except:
        return None

def postprocess(d: dict) -> dict:
    out = {}
    out["section"] = d.get("section") or "expense_details"
    out["subgroup"] = d.get("subgroup")
    out["item"] = d.get("item")
    out["description"] = d.get("description")
    fx = d.get("formula") or {}
    up = cint(fx.get("unit_price") or 0) or 0
    qt = cint(fx.get("quantity") or 1) or 1
    tm = cint(fx.get("times") or 1) or 1
    out["formula"] = {"unit_price": up, "quantity": qt, "times": tm}
    amt = cint(d.get("amount_expected"))
    if not amt: amt = up * qt * tm
    out["amount_expected"] = amt
    out["reason"] = d.get("reason") or ""
    out["evidence"] = d.get("evidence") or []
    out["warnings"] = d.get("warnings") or []
    return out

# ---- DB: rule_chunk / rule_embedding ----
def fetch_rules_topk_from_db(query: str, dsn: str, version: str|None, k: int,
                             embed_client: OpenAI|None, embed_model: str|None):
    """
    pgvector 존재시: 임베딩 유사도 Top-K
    없으면: LIKE 폴백
    """
    import psycopg2
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    # pgvector 존재 확인
    cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector');")
    has_vector = cur.fetchone()[0]

    topk = []

    if has_vector and embed_client:
        # 임베딩 모델로 질의 임베딩 생성
        em = embed_client.embeddings.create(model=embed_model or "solar-embedding-1-large",
                                            input=query)
        qvec = em.data[0].embedding  # list[float]

        # 유사도 쿼리
        sql = """
        SELECT rc.ord, rc.path, rc.text, 1 - (re.embedding <=> %s) AS score
        FROM rule_embedding re
        JOIN rule_chunk rc ON rc.id = re.rule_chunk_id
        WHERE (%s IS NULL OR rc.version = %s)
        ORDER BY re.embedding <=> %s ASC
        LIMIT %s;
        """
        params = (qvec, version, version, qvec, k)
        cur.execute(sql, params)
        for ord_, path, text, score in cur.fetchall():
            snippet = (text or "")[:160].replace("\n"," ")
            topk.append({"ord": ord_ or 0, "path": path or "", "quote": snippet, "score": float(score or 0)})
    else:
        # 폴백: LIKE 검색
        sql = """
        SELECT rc.ord, rc.path, rc.text
        FROM rule_chunk rc
        WHERE (%s IS NULL OR rc.version = %s)
          AND (rc.text ILIKE '%%' || %s || '%%' OR rc.path ILIKE '%%' || %s || '%%')
        ORDER BY LENGTH(rc.text) ASC
        LIMIT %s;
        """
        params = (version, version, query, query, k)
        cur.execute(sql, params)
        for ord_, path, text in cur.fetchall():
            snippet = (text or "")[:160].replace("\n"," ")
            topk.append({"ord": ord_ or 0, "path": path or "", "quote": snippet})

    cur.close()
    conn.close()
    return topk

def main():
    load_dotenv()

    ap = ArgumentParser()
    ap.add_argument("query", help='예: "개강총회 다과 6만원, 예산안에는?"')
    ap.add_argument("--db", help='Postgres DSN (없으면 $POSTGRES_DSN 사용)', default=None)
    ap.add_argument("--policy-version", help="세칙 버전 필터(예: 2024-10-28)", default=None)
    ap.add_argument("--embed-model", default=os.getenv("OPENAI_EMBED_MODEL","solar-embedding-1-large"))
    ap.add_argument("--k", type=int, default=3, help="세칙 Top-K (기본 3)")
    args = ap.parse_args()

    if not PROFILE_PATH.exists():
        print(f"❌ {PROFILE_PATH} 가 없습니다. 먼저 template_to_profile.py 를 실행하세요.")
        sys.exit(1)

    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

    # Upstage/OpenAI 설정
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("UPSTAGE_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.upstage.ai/v1")
    model = os.getenv("OPENAI_MODEL", "solar-1-mini-chat")
    embed_model = os.getenv("OPENAI_EMBED_MODEL", "solar-embedding-1-large")
    if not api_key:
        print("❌ OPENAI_API_KEY(=UPSTAGE_API_KEY)가 필요합니다.")
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url=base_url)

    # DB에서 세칙 Top-K 조회 (있는 경우)
    dsn = args.db or os.getenv("POSTGRES_DSN")
    topk = []
    if dsn:
        try:
            topk = fetch_rules_topk_from_db(
                query=args.query,
                dsn=dsn,
                version=args.policy_version,
                k=args.k,
                embed_client=client,
                embed_model=embed_model
            )
        except Exception as e:
            print("⚠️ DB 세칙 조회 실패:", e)

    # 프롬프트 구성
    system = (
        "너는 대학 학생회 예산안 작성 보조 도구다. "
        "세칙 위반 제안은 하지 말고, 반드시 지정된 JSON 스키마로만 단일 객체를 출력하라."
    )
    parts = [
        "[질문]", args.query,
        "\n[템플릿 표준 컬럼 프로필]",
        json.dumps(profile, ensure_ascii=False),
        "\n[출력 형식(JSON 스키마)]",
        json.dumps(SCHEMA_HINT, ensure_ascii=False),
        "\n규칙:",
        "- 위 스키마의 키만 사용하여 하나의 JSON 객체를 출력할 것.",
        "- 금액은 원 단위 정수.",
        "- 가능하면 formula(단가/수량/횟수)도 채울 것.",
        "- evidence는, 제공된 세칙 후보에서 적절한 것을 우선 포함할 것. 없으면 빈 배열([])."
    ]
    if topk:
        parts += ["\n[세칙 근거 후보 Top-K]", json.dumps(topk, ensure_ascii=False, indent=2)]
    prompt = "\n".join(parts)

    # LLM 호출
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role":"system","content":system},
                  {"role":"user","content":prompt}],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content.strip()
    data = postprocess(json.loads(strip_json(raw)))

    # 모델이 비워두면 Top-K 일부 보강
    if not data.get("evidence") and topk:
        data["evidence"] = [{"ord": t["ord"], "path": t["path"], "quote": t["quote"]} for t in topk[:2]]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ compose_result.json 저장: {RESULT_PATH}")
    print(json.dumps(data, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
