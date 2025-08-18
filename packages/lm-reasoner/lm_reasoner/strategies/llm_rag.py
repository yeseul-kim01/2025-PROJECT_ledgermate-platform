# packages/lm-reasoner/lm_reasoner/strategies/llm_rag.py
from __future__ import annotations
from .base import RecommenderStrategy
from ..types import Receipt, Recommendation, Evidence
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("UPSTAGE_API_KEY"),
                base_url="https://api.upstage.ai/v1")
MODEL = "solar-pro-2"  # 실제 모델명 확인

PROMPT = """너는 회칙 근거로 영수증 분류코드를 결정한다.
반드시 JSON으로만 답하라: {"code": str|null, "code_confidence": float, "rationale": str}
불확실하면 code=null, confidence<0.5.
"""

def format_ctx(chunks):
    return "\n\n".join([f"[{c['ord']}] {(c['path'] or '')}\n{c['text']}" for c in chunks])

from ..registry import register
from lm_store.pg import connect

@register
class LLMRAGStrategy(RecommenderStrategy):
    name = "llm_rag"

    def recommend(self, *, receipt: Receipt, policy_id: str, k: int = 8) -> Recommendation:
        # 간단 검색 재활용
        cues = [receipt.fields.get("memo"), receipt.fields.get("merchant")]
        with connect() as conn:
            rows = conn.execute(
                """select ord, path, text
                   from rule_chunk
                   where policy_id=%s and (text ilike %s or text ilike %s)
                   order by ord asc limit %s""",
                (policy_id, f"%{cues[0] or ''}%", f"%{cues[1] or ''}%", k)
            ).fetchall()
        ctx = format_ctx(rows)
        user = f"영수증: {receipt.fields}\n\n관련 규정:\n{ctx}"

        res = client.chat.completions.create(
            model=MODEL, temperature=0,
            response_format={"type":"json_object"},
            messages=[{"role":"system","content":PROMPT},
                      {"role":"user","content":user}]
        )
        parsed = res.choices[0].message.parsed
        code = parsed.get("code")
        conf = float(parsed.get("code_confidence", 0.0))
        rat  = parsed.get("rationale","")
        ev = [Evidence(kind="chunk", ref=r["ord"], preview=(r["path"] or "")+" :: "+r["text"][:120]) for r in rows]
        return Recommendation(code=code, confidence=conf, rationale=rat, evidence=ev, provider=self.name)
