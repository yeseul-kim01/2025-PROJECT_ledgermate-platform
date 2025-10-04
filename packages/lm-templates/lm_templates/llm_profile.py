# packages/lm-templates/llm_profile.py
from __future__ import annotations
import json, re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openai import OpenAI  # pip install openai==1.81.0

# ---------- LLM 클라이언트 ----------
def make_upstage_client(api_key: str | None = None) -> OpenAI:
    """
    Upstage(OpenAI 호환) 클라이언트 생성
    """
    return OpenAI(
        api_key=api_key or "UPSTAGE_API_KEY",
        base_url="https://api.upstage.ai/v1"
    )

# ---------- 입력 템플릿 JSON 요약(프롬프트 경량화) ----------
@dataclass
class TableSketch:
    table_id: int
    page: int
    title_hint: str
    headers: List[str]

def _extract_table_headers_from_html(html: str) -> List[str]:
    # 간단 파서(BeautifulSoup 없이 가볍게): thead가 있으면 그 안쪽의 첫 tr td|th 텍스트를 추출
    # 텍스트는 매우 단순 추출
    thead_match = re.search(r"<thead>(.*?)</thead>", html, flags=re.S|re.I)
    block = thead_match.group(1) if thead_match else html
    tr_match = re.search(r"<tr>(.*?)</tr>", block, flags=re.S|re.I)
    if not tr_match:
        return []
    row_html = tr_match.group(1)
    cells = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row_html, flags=re.S|re.I)
    cleaned = []
    for c in cells:
        # 간단 텍스트 정리 (태그 제거)
        txt = re.sub(r"<.*?>", "", c)
        txt = txt.replace("\n", " ").strip()
        if not txt:
            continue
        # colspan 보정은 LLM에 맡길 수 있음 (간단화)
        cleaned.append(txt)
    return cleaned

def _closest_title(elements: List[Dict[str, Any]], table_index: int) -> str:
    table_el = elements[table_index]
    page = table_el.get("page")
    # 같은 페이지에서 테이블 앞쪽의 가장 최근 heading/paragraph 텍스트
    for j in range(table_index - 1, -1, -1):
        prev = elements[j]
        if prev.get("page") != page:
            break
        if prev.get("category") in ("heading1", "heading2", "paragraph"):
            txt = ((prev.get("content") or {}).get("text") or "").strip()
            if txt:
                return txt
    return ""

def summarize_template_for_llm(template_json: Dict[str, Any]) -> Dict[str, Any]:
    elements = template_json.get("elements", [])
    pages = int((template_json.get("usage") or {}).get("pages") or 0)

    sketches: List[Dict[str, Any]] = []
    for i, el in enumerate(elements):
        if el.get("category") != "table":
            continue
        html = ((el.get("content") or {}).get("html") or "")
        headers = _extract_table_headers_from_html(html)
        title = _closest_title(elements, i)
        sketches.append({
            "table_id": el.get("id"),
            "page": el.get("page"),
            "title_hint": title,
            "headers": headers
        })

    # 문서 레벨 요약(제목/본문 앞부분)
    doc_title = ""
    for el in elements[:6]:  # 앞쪽만 훑기
        if el.get("category") in ("heading1", "heading2"):
            t = ((el.get("content") or {}).get("text") or "").strip()
            if t:
                doc_title = t
                break

    return {
        "pages": pages,
        "doc_title": doc_title,
        "tables": sketches
    }

# ---------- LLM 프롬프트 ----------
SYSTEM_PROMPT = """너는 대학 학생회 결산문서 템플릿을 구조적으로 해석하여,
'자동 채움이 가능한 데이터 스키마'와 '문서의 표 역할'을 JSON으로 정의하는 전문가다.
항상 '유효한 JSON'만 출력하라. 주석/설명 문구/코드펜스는 금지한다.
"""

USER_PROMPT_TMPL = """아래는 결산안 템플릿의 요약정보다(테이블 헤더/근접 제목/페이지 수).
이 정보만으로 테이블의 '역할'과 '컬럼 매핑', 그리고 자동 채움 대상/집계 대상을 도출하라.
또한 '영수증 1건당 LLM이 출력해야 하는 고정 스펙(PerReceiptOutputSpec)'도 함께 정의하라.

요구사항:
1) tables[*].role 은 다음 중 가능한 값으로 추론: 
   - "ledger_details"(세부 결산 장부: No/일시/코드/세부내역/거래명/수입/지출/잔액…)
   - "expense_details_by_field"(분야·비목별 세부 지출 표)
   - "expense_summary"(세출 요약)
   - "revenue_summary"(세입 요약)
   - 위에 딱 맞지 않으면 "unknown"
2) tables[*].mapping 은 표준키 ↔ 실제 헤더명을 매핑.
   표준키 후보:
   - 행단위 공통: date, account_code, summary, amount, vat, evidence, notes
   - 장부형(ledger): no, date, code, detail, merchant, income, expense, balance, notes
   - 요약형(summary): amount, change_rate, memo 등
3) fill_plan.auto_fill 에는 '영수증 → 한 행 생성'이 가능한 role을 넣는다 (보통 ledger_details, expense_details_by_field).
   fill_plan.aggregations 에는 집계로 채우는 요약 테이블(role)을 넣는다 (revenue_summary, expense_summary).
4) per_receipt_output_spec 은 LLM이 '영수증 1건당' 반환해야 하는 JSON 스키마(키/설명/예시)를 정의한다.
   - 필수 키: receipt, classification, policy_refs, budget_match, compliance, settlement_row
   - settlement_row 는 문서 표에 꽂힐 최종 한 행(date/account_code/summary/amount 등)
5) 반드시 아래 JSON 스키마로만 출력:
{
  "schema_version": "1.0.0",
  "profile_id": "auto:{name}:v1",
  "source": { "pages": <int>, "tables": [{"id": <int>, "title": <string>}] },
  "render_rules": { "date_format": "yyyy-MM-dd", "currency_format": "#,###", "zero_as_dash": true },
  "tables": { "<role or unknown>": { "table_id": <int> or null or list, "role": "<role>", "header": [<string>], "mapping": { "<std_key>": "<header_name>" }, "page": <int> or null } or list },
  "fill_plan": { "auto_fill": [<role>], "aggregations": [<role>], "manual_or_static": [<string>] },
  "per_receipt_output_spec": {
    "description": "영수증 1건당 LLM 출력 스펙",
    "required_keys": ["receipt","classification","policy_refs","budget_match","compliance","settlement_row"],
    "keys": {
      "receipt": {"desc":"OCR 정규화 결과", "fields":["date","merchant","amount_total","vat","items[]","payment_method"]},
      "classification": {"desc":"비목/코드/신뢰도","fields":["category_path","account_code","confidence","reasons[]"]},
      "policy_refs": {"desc":"세칙 근거","fields":["doc","version","section","page","snippet"]},
      "budget_match": {"desc":"예산 라인 매칭","fields":["line_title","line_code","remaining_amount"]},
      "compliance": {"desc":"컴플라이언스 체크","fields":["vat_required","vat_present","limits[]","missing_docs[]"]},
      "settlement_row": {"desc":"최종 결산표 한 행","fields":["date","account_code","summary","amount","vat","evidence","notes"]}
    },
    "example": {
      "receipt":{"date":"2024-11-02","merchant":"스타벅스 부산대점","amount_total":35000,"vat":3182,"items":[{"name":"아메리카노 외 4","qty":5}]},
      "classification":{"category_path":"회의비>간담회비","account_code":"510-110","confidence":0.86,"reasons":["카페/음료 키워드"]},
      "policy_refs":[{"doc":"재정운용세칙","version":"2024-10-28","section":"§3.2","page":12,"snippet":"간담회비 허용…"}],
      "budget_match":{"line_title":"간담회비","line_code":"B-510-110","remaining_amount":1200000},
      "compliance":{"vat_required":true,"vat_present":true,"limits":[{"type":"per_event","limit":100000,"ok":true}],"missing_docs":[]},
      "settlement_row":{"date":"2024-11-02","account_code":"510-110","summary":"간담회비(운영회의) - 스타벅스","amount":35000,"vat":3182,"evidence":"영수증·전표","notes":"참석 5인, §3.2"}
    }
  }
}

입력 요약:
<INPUT_JSON_SUMMARY>
"""

def _strip_code_fences(s: str) -> str:
    s = re.sub(r"^```(json)?", "", s.strip(), flags=re.I)
    s = re.sub(r"```$", "", s.strip(), flags=re.I)
    return s.strip()

def _coerce_json(text: str) -> Dict[str, Any]:
    text = _strip_code_fences(text)
    # 흔한 실수 보정: 마지막 쉼표, true/false 대문자 등은 Solar에서 잘 맞춰줌. 여기서는 단순 파싱만.
    return json.loads(text)

def infer_profile_with_llm(
    template_raw_json_path: str | Path,
    api_key: str | None = None,
    profile_name_hint: str | None = None,
    model: str = "solar-pro2",
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """
    Upstage Solar Pro에게 템플릿 구조 해석을 맡겨 '프로필+PerReceiptOutputSpec'을 생성.
    """
    raw = json.loads(Path(template_raw_json_path).read_text(encoding="utf-8"))
    summary = summarize_template_for_llm(raw)

    name = profile_name_hint or Path(template_raw_json_path).stem
    user_prompt = USER_PROMPT_TMPL.replace("<INPUT_JSON_SUMMARY>", json.dumps(summary, ensure_ascii=False, indent=2))
    user_prompt = user_prompt.replace("{name}", name)

    client = make_upstage_client(api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        reasoning_effort="high",
        stream=False,
        # JSON 강제 (OpenAI 호환). Upstage도 지원됨.
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content
    try:
        data = _coerce_json(content)
    except Exception:
        # response_format 미적용/코드펜스 등 대비, 소프트 파싱 재시도
        data = _coerce_json(_strip_code_fences(content))

    # 최소 필드 보정
    data.setdefault("schema_version", "1.0.0")
    data.setdefault("render_rules", {"date_format": "yyyy-MM-dd", "currency_format": "#,###", "zero_as_dash": True})
    if "source" not in data:
        data["source"] = {"pages": summary.get("pages", 0), "tables": [{"id": t["table_id"], "title": t["title_hint"]} for t in summary["tables"]]}

    return data

def save_inferred_profile(
    template_raw_json_path: str | Path,
    out_path: str | Path,
    api_key: str | None = None,
    profile_name_hint: str | None = None,
) -> Path:
    prof = infer_profile_with_llm(template_raw_json_path, api_key=api_key, profile_name_hint=profile_name_hint)
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    return outp
