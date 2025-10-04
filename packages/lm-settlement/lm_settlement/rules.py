# packages/lm-settlement/lm_settlement/rules.py
from __future__ import annotations
from typing import Dict, Any, List

ONTOLOGY = [
    (["회의","간담","미팅","분임","세미나"], "회의비>간담회비", "510-110"),
    (["커피","카페","스타벅스","이디야","음료","빵","다과"], "회의비>간담회비", "510-110"),
    (["사무용품","볼펜","복사용지","문구","토너"], "운영비>소모품비", "511-120"),
    (["인쇄","출력","홍보물","배너","현수막"], "사업비>홍보비", "611-130"),
    # 관람권/경품 류는 여기서도 줄 수 있지만, 이제 LLM이 주도하니 없어도 됨
]

def rule_candidates(receipt: Dict[str, Any], topn=3) -> List[Dict[str, Any]]:
    text = " ".join([
        receipt.get("merchant",""),
        receipt.get("memo",""),
        " ".join(i.get("name","") for i in receipt.get("items",[]))
    ]).lower()
    out = []
    for kws, cat, code in ONTOLOGY:
        hit = sum(1 for k in kws if k in text)
        if hit > 0:
            out.append({
                "category_path": cat,
                "score": 0.6 + 0.05*min(hit,4),
                "code_hint": code,
                "reasons": [f"키워드:{','.join([k for k in kws if k in text])}"]
            })
    # ← 폴백 제거: 비어있을 수 있음
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:topn]
