# packages/lm-settlement/lm_settlement/pipeline.py
from __future__ import annotations
import os, json
from typing import Dict, Any
from openai import OpenAI
from lm_rag.retriever import RAG
from .rules import rule_candidates  # ← 당분간 유지(비어도 OK)
from .prompts import SYSTEM, USER_TMPL


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

    extra_guidance = (
        "분류(rule_topn)가 비어있거나 신뢰도가 낮으면, 영수증 텍스트와 규정 정의만으로도 "
        "account_name을 스스로 추론하세요. 세칙 제16조 ④-4에 따라 관람권/티켓/상품권/경품/기념품 등 "
        "회원에게 제공되는 물품·현금은 '상품비'로 분류합니다. "
        "사업분야가 불명확하면 비목만 기입해도 됩니다. "
        "임의로 '운영비>기타'로 폴백하지 말고, 근거 없으면 null을 허용하세요. "
        "policy_refs/budget_refs는 점수 상위 1~3개만 포함하고 문서명 확장자는 제거하세요. "
        "예산 라인 코드가 회계 코드 패턴과 다르면 account_code는 null로 두세요."
    )

    topn = rule_candidates(receipt)  # 힌트 용
    rag = RAG(org_id=org_id)

    # 질의어 구성(비었으면 안전 기본어)
    items_text = " ".join(i.get("name","") for i in receipt.get("items",[])).strip()
    query_parts = [
        receipt.get("merchant","") or "",
        receipt.get("memo","") or "",
        items_text or "",
        receipt.get("raw_text","") or ""
    ]
    query = " ".join(p for p in query_parts if p).strip() or "일반 지출"

    policies = rag.search_rules(query_text=query)[:3]
    budgets  = rag.search_budget_lines(category_hint=(topn[0]["category_path"] if topn else None),
                                       query_text=query)[:3]

    # 3) LLM 호출
    client = upstage_client(api_key)
    user = USER_TMPL.format(
        org_id=org_id,
        fiscal_period=fiscal_period,
        extra_guidance=extra_guidance,
        receipt=json.dumps(receipt, ensure_ascii=False, indent=2),
        rule_topn=json.dumps(topn, ensure_ascii=False, indent=2),
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

    # 4) 안전 보정
    data.setdefault("receipt", receipt)
    if "settlement_row" in data:
        sr = data["settlement_row"]
        sr.setdefault("date", receipt.get("date"))
        sr.setdefault("amount", receipt.get("amount_total"))
        sr.setdefault("vat", receipt.get("vat"))
        sr.setdefault("payment_method", receipt.get("payment_method"))
    return data
