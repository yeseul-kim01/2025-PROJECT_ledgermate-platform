# packages/lm-settlement/lm_settlement/pipeline.py
from __future__ import annotations
import os, json
from typing import Dict, Any
from openai import OpenAI
from lm_rag.retriever import RAG
from .prompts import SYSTEM, USER_TMPL
from .extract_budget_outline import load_budget_outline, outline_text, find_code_by_path

def upstage_client(api_key: str | None = None):
    return OpenAI(api_key=api_key or os.getenv("UPSTAGE_API_KEY"),
                  base_url="https://api.upstage.ai/v1")



def build_profile_mapping(profile: Dict[str,Any]) -> Dict[str,Any]:
    tables = profile.get("tables",{})
    ed = tables.get("expense_details_by_field") or {}
    ld = tables.get("ledger_details") or {}
    return {
        "expense_details_by_field": {
            "mapping": ed.get("mapping"),
            "code_extract_rules": ed.get("code_extract_rules")
        },
        "ledger_details": {
            "mapping": ld.get("mapping")
        }
    }

def settle(receipt: Dict[str, Any],
           profile: Dict[str, Any],
           org_id: str, fiscal_period: str,
           api_key: str | None = None) -> Dict[str, Any]:
    outline = load_budget_outline(org_id)
    budget_outline_txt = outline_text(outline)
    extra_guidance = (
        "세칙 제16조 ④-4: 관람권/티켓/상품권/경품/기념품 등 회원에게 제공되는 물품·현금은 '상품비'로 분류. "
        "근거가 불충분하면 임의 폴백 금지(null 허용). "
        "detail은 가능하면 상호명을 앞에 붙이세요. 예) '쿠프마케팅, 1인 관람권, 13,000원'. "
        "예산 라인 코드가 회계 코드 패턴과 다르면 account_code는 null로 두세요. "
        "가능하면 예산 코드 아웃라인에서 일치하는 경로의 정규 코드(예: 711)를 사용하세요."
        "policy_refs/budget_refs는 점수 상위 1~3개만 포함하고 문서명 확장자는 제거하세요."
    )

    # ── RAG: 영수증 전체 텍스트 기반 질의
    rag = RAG(org_id=org_id)
    query_parts = [
        receipt.get("merchant","") or "",
        receipt.get("memo","") or "",
        " ".join(i.get("name","") for i in receipt.get("items",[]) if i.get("name")) or "",
        receipt.get("raw_text","") or ""
    ]
    query = " ".join(p for p in query_parts if p).strip() or "일반 지출"

    policies = rag.search_rules(query_text=query)[:3]
    budgets  = rag.search_budget_lines(query_text=query)[:3]

    # ── LLM 호출
    client = upstage_client(api_key)
    user = USER_TMPL.format(
        org_id=org_id,
        fiscal_period=fiscal_period,
        extra_guidance=extra_guidance,
        budget_outline_text=budget_outline_txt,
        receipt=json.dumps(receipt, ensure_ascii=False, indent=2),
        policies=json.dumps(policies, ensure_ascii=False, indent=2),
        budgets=json.dumps(budgets, ensure_ascii=False, indent=2),
        profile_mapping=json.dumps(build_profile_mapping(profile), ensure_ascii=False, indent=2),
    )
    resp = client.chat.completions.create(
        model=os.getenv("UPSTAGE_LLM_MODEL","solar-pro2"),
        messages=[{"role":"system","content":SYSTEM},
                  {"role":"user","content":user}],
        temperature=0.2,
        reasoning_effort="high",
        response_format={"type":"json_object"},
    )
    data = json.loads(resp.choices[0].message.content)

    # ── 안전 보정
    data.setdefault("receipt", receipt)
    if "settlement_row" in data:
        sr = data.get("settlement_row", {})
        if sr is not None and sr.get("account_code") is None:
            for b in budgets:
                c = (b or {}).get("line_code")
                if c and re.match(r'^\d{3}(?:-\d{3}(?:-\d{3})?)?$', c):
                    sr["account_code"] = c
                    break
        sr.setdefault("date", receipt.get("date"))
        sr.setdefault("amount", receipt.get("amount_total"))
        sr.setdefault("vat", receipt.get("vat"))
        sr.setdefault("payment_method", receipt.get("payment_method"))
        if (not sr.get("account_code")) and sr.get("account_name"):
            code = find_code_by_path(outline, sr["account_name"])
            if code:
                sr["account_code"] = code
    return data
