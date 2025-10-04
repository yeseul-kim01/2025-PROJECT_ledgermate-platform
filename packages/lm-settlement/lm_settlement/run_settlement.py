#packages/lm-settlement/lm_settlement/run_settlement.py
from __future__ import annotations
import os, json, glob, pathlib
from typing import Dict, Any, List, Tuple
from lm_settlement.pipeline import settle  # ← 맞는 경로
import re 

BILLS_DIR = "out/bills"
OUT_DIR = "out/settled"
ORG_ID = "demo.univ"
FISCAL_PERIOD = "2024-H2"


def _to_number(v):
    if isinstance(v, (int, float)): return v
    if isinstance(v, str):
        s = v.replace(",", "").replace("원", "").strip()
        try: return float(s)
        except: return None
    return None


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _pick_bill_pair() -> List[Tuple[str, str | None]]:
    """
    bills 디렉토리에서 *.ocr.json / *.raw.json 페어를 추출.
    반환: [(base, ocr_path or None), ...]  (raw는 같은 base로 자동 탐색)
    """
    paths = glob.glob(os.path.join(BILLS_DIR, "*.ocr.json")) + \
            glob.glob(os.path.join(BILLS_DIR, "*.raw.json"))
    bases = {}
    for p in paths:
        base = pathlib.Path(p).name.replace(".ocr.json", "").replace(".raw.json", "")
        d = bases.setdefault(base, {"ocr": None, "raw": None})
        if p.endswith(".ocr.json"):
            d["ocr"] = p
        else:
            d["raw"] = p
    out = []
    for base, pr in bases.items():
        # ocr 우선, 없으면 raw만이라도
        if pr["ocr"]:
            out.append((base, pr["ocr"]))
        elif pr["raw"]:
            out.append((base, pr["raw"]))
    return out

def _extract_text(doc: Dict[str, Any]) -> str:
    if isinstance(doc.get("full_text"), str) and doc["full_text"].strip():
        return doc["full_text"]
    if isinstance(doc.get("pages"), list):
        parts = [p.get("text","") for p in doc["pages"] if isinstance(p, dict)]
        return "\n".join([t for t in parts if t])
    return ""

def _find_date(text: str) -> str | None:
    m = re.search(r"(20\d{2})[.\-/년 ]\s*(\d{1,2})[.\-/월 ]\s*(\d{1,2})", text)
    if not m: return None
    y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{y:04d}-{mth:02d}-{d:02d}"

def _find_amount(text: str) -> float | None:
    # 라벨 기반
    for lab in ["합계금액", "결제금액", "총매출액", "총액", "합 계", "합계"]:
        m = re.search(lab + r".{0,12}?([\d]{1,3}(?:[,]\d{3})+|\d{4,})", text)
        if m:
            s = m.group(1).replace(",", "")
            try: return float(s)
            except: pass
    # 가장 큰 통화형 숫자 폴백(전화번호 등 제외)
    nums = [n.replace(",", "") for n in re.findall(r"(?<!\d)(\d{1,3}(?:,\d{3})+)(?!\d)", text)]
    cand = [int(n) for n in nums if len(n) >= 4]
    return float(max(cand)) if cand else None

def _find_vat(text: str) -> float | None:
    m = re.search(r"(부\s*가\s*세|부가세)\s*[: ]?\s*([\d]{1,3}(?:,\d{3})+|\d{1,7})", text, re.IGNORECASE)
    if not m: return None
    try: return float(m.group(2).replace(",", ""))
    except: return None

_BRANDS = [
    "버거킹","burger king","burger","와퍼","던킨","dunkin","donut","도넛",
    "스타벅스","starbucks","이디야","투썸","베스킨","던킨도너츠"
]

def _guess_merchant(text: str) -> str:
    low = text.lower()
    for b in _BRANDS:
        if b in low: return b.title() if b.isalpha() else b
    # 첫 줄 근처 짧은 대문자/한글 상호 폴백
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        if len(line) <= 25 and not any(x in line for x in ["사업자","대표","주소","전화","고객센터"]):
            return line
    return ""

def _guess_payment(text: str) -> str | None:
    if "현금" in text: return "현금"
    if "카드" in text: return "카드"
    if "선결제" in text or "배달의민족" in text or "요기요" in text or "쿠팡이츠" in text:
        return "기타"
    return None

def _parse_items(text: str) -> List[Dict[str, Any]]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^\*?([^\d@][^\d]{1,40}?)\s+(\d+)\s+(\d{1,3}(?:,\d{3})+|\d+)$", line)
        if m:
            name, qty, total = m.group(1).strip(), int(m.group(2)), m.group(3).replace(",", "")
            items.append({"name": name, "qty": qty, "total": float(total)})
    return items

def _normalize_receipt(doc: Dict[str, Any]) -> Dict[str, Any]:
    raw = _extract_text(doc)
    # 기존 로직으로 한번 시도
    def pick(d: Dict[str, Any], *keys, default=None):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    # 기존 키가 있으면 우선
    amount_total = _to_number(pick(doc, "amount_total", "total", "총액", "결제금액"))
    vat          = _to_number(pick(doc, "vat", "tax", "부가세", default=0)) or None
    date         = pick(doc, "date", "paid_at", "datetime", "거래일시")

    if amount_total is None: amount_total = _find_amount(raw)
    if vat is None:          vat = _find_vat(raw) or 0
    if not date:             date = _find_date(raw)

    items = pick(doc, "items", "line_items", "details", default=[]) or []
    if not items:
        items = _parse_items(raw)

    merchant = pick(doc, "merchant", "store", "vendor", "상호명", default="")
    if not merchant:
        merchant = _guess_merchant(raw)
    payment  = pick(doc, "payment_method", "method", "card_type", default=None)
    if not payment:
        payment = _guess_payment(raw)

    receipt = {
        "merchant": pick(doc, "merchant", "store", "vendor", "상호명", default=""),
        "date":     pick(doc, "date", "paid_at", "datetime", "거래일시"),
        "amount_total": amount_total,
        "vat":      vat,
        "payment_method": pick(doc, "payment_method", "method", "card_type", default=None),
        "memo":     pick(doc, "memo", "note", "비고", default=""),
        "items":    items,
        "raw_text": pick(doc, "raw_text", "full_text", default="")  # ← 원문 보존
    }
    # 아이템 합으로 보정
    if receipt["amount_total"] is None and items:
        s = sum(_to_number(it.get("total")) or 0 for it in items)
        receipt["amount_total"] = s if s > 0 else None
    return receipt

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pairs = _pick_bill_pair()
    if not pairs:
        print("No bills found in", BILLS_DIR)
        return

    # org_id 기준 RAG 테넌트 필터를 쓰고 싶으면, settle() 내부 RAG 생성부를 수정해도 되고
    # 아니면 여기서 환경변수로 넘길 수도 있음.
    for base, path in pairs:
        doc = _load_json(path)
        receipt = _normalize_receipt(doc)
        # 프로파일은 프로젝트에 맞춰 로드하세요. 여기선 최소 골격.
        profile = {
            "tables": {
                "expense_details_by_field": {
                    "mapping": {"date":"date","amount":"amount_total","vat":"vat"},
                    "code_extract_rules": []
                },
                "ledger_details": {"mapping": {"account_code":"account_code","detail":"detail"}}
            }
        }
        result = settle(receipt, profile, org_id=ORG_ID, fiscal_period=FISCAL_PERIOD)
        out_path = os.path.join(OUT_DIR, f"{base}.settle.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ {base}: {out_path}")

if __name__ == "__main__":
    main()
