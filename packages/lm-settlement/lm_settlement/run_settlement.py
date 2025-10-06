# packages/lm-settlement/lm_settlement/run_settlement.py
from __future__ import annotations
import os, json, glob, pathlib, re
from typing import Dict, Any, List, Tuple
from lm_settlement.pipeline import settle

BILLS_DIR = "out/bills"
OUT_DIR = "out/settled"
ORG_ID = "demo.univ"
FISCAL_PERIOD = "2024-H2"


_BRANDS = [
    "버거킹","burger king","burger","와퍼","던킨","dunkin","donut","도넛",
    "스타벅스","starbucks","이디야","투썸","베스킨","던킨도너츠"
]

def _guess_merchant(text: str) -> str:
    low = text.lower()
    for b in _BRANDS:
        if b in low:
            # 영문은 타이틀케이스, 한글/혼합은 원문 반환
            return b.title() if all('a' <= ch <= 'z' for ch in b.lower().replace(" ", "")) else b
    # 첫 줄 근처의 짧은 상호 후보
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        if len(line) <= 25 and not any(x in line for x in ["사업자","대표","주소","전화","고객센터"]):
            return line
    return ""

def _guess_payment(text: str) -> str | None:
    if "현금" in text: return "현금"
    if "카드" in text: return "카드"
    if any(k in text for k in ["선결제","배달의민족","요기요","쿠팡이츠","네이버주문","카카오페이"]):
        return "기타"
    return None

# --- 새 함수: 2줄 품목 파서 ---
def _parse_items_two_line(text: str) -> List[Dict[str, Any]]:
    lines = [l.strip() for l in text.splitlines()]
    items = []
    for i, line in enumerate(lines):
        if not line:
            continue
        if line.startswith("*") or line.startswith("•"):
            name = re.sub(r"^[*•]\s*", "", line).strip()
            if i + 1 < len(lines):
                m = re.match(r"^(\d{1,3})\s+(\d{1,3}(?:,\d{3})+|\d+)$", lines[i+1])
                if m:
                    qty = int(m.group(1))
                    total = float(m.group(2).replace(",", ""))
                    items.append({"name": name, "qty": qty, "total": total})
    return items



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

def _find_first(pattern: str, text: str):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None

def _find_date(text: str) -> str | None:
    m = re.search(r'(20\d{2})[.\-/년 ]\s*(\d{1,2})[.\-/월 ]\s*(\d{1,2})', text)
    if m:
        y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mth:02d}-{d:02d}"
    return None

def _find_amount(text: str) -> float | None:
    for lab in ["합계금액", "결제금액", "총매출액", "총 금액", "총금액", "총액", "합 계", "합계"]:
        m = re.search(lab + r".{0,12}?([\d]{1,3}(?:[,]\d{3})+|\d{4,})", text)
        if m:
            try: return float(m.group(1).replace(",", ""))
            except: pass
    nums = [n.replace(",", "") for n in re.findall(r"(?<!\d)(\d{1,3}(?:,\d{3})+)(?!\d)", text)]
    cand = [int(n) for n in nums if len(n) >= 4]
    return float(max(cand)) if cand else None

def _find_vat(text: str) -> float | None:
    m = re.search(r"(부\s*가\s*세|부가세)\s*[: ]?\s*([\d]{1,3}(?:,\d{3})+|\d{1,7})", text, re.IGNORECASE)
    if m:
        try: return float(m.group(2).replace(",", ""))
        except: return None
    return None

def _find_merchant(text: str) -> str | None:
    for pat in [r"판매업체\s*상호\s*([^\n]+)", r"상호\s*[: ]\s*([^\n]+)"]:
        m = re.search(pat, text)
        if m: return m.group(1).strip()
    return None

def _guess_payment(text: str) -> str | None:
    if "현금" in text: return "현금"
    if any(t in text for t in ["체크", "신용", "카드"]): return "카드"
    if any(t in text for t in ["이체", "계좌이체"]): return "이체"
    return None

def _parse_items(text: str) -> List[Dict[str, Any]]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^\*?([^\d@][^\d]{1,40}?)\s+(\d+)\s+(\d{1,3}(?:,\d{3})+|\d+)$", line)
        if m:
            name, qty, total = m.group(1).strip(), int(m.group(2)), m.group(3).replace(",", "")
            items.append({"name": name, "qty": qty, "total": float(total)})
    # ← 한 줄 정규식에 안 걸린 케이스(버거킹) 보완
    if not items:
        items = _parse_items_two_line(text)
    return items
def _normalize_receipt(doc: Dict[str, Any]) -> Dict[str, Any]:
    raw = _extract_text(doc)

    def pick(d: Dict[str, Any], *keys, default=None):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    amount_total = _to_number(pick(doc, "amount_total", "total", "총액", "결제금액"))
    vat          = _to_number(pick(doc, "vat", "tax", "부가세", default=0)) or None
    date         = pick(doc, "date", "paid_at", "datetime", "거래일시")

    if amount_total is None: amount_total = _find_amount(raw)
    if vat is None:          vat = _find_vat(raw) or 0
    if not date:             date = _find_date(raw)

    items = pick(doc, "items", "line_items", "details", default=[]) or []
    if not items:
        items = _parse_items(raw)

    # ▼ 추정
    merchant_guess = pick(doc, "merchant", "store", "vendor", "상호명", default="") or _guess_merchant(raw)
    payment_guess  = pick(doc, "payment_method", "method", "card_type", default=None) or _guess_payment(raw)

    receipt = {
        "merchant": merchant_guess,             # ← 추정값 사용
        "date":     date,
        "amount_total": amount_total,
        "vat":      vat,
        "payment_method": payment_guess,        # ← 추정값 사용
        "memo":     pick(doc, "memo", "note", "비고", default=""),
        "items":    items,
        "raw_text": pick(doc, "raw_text", "full_text", default=raw)  # 원문 보존
    }
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

    for base, path in pairs:
        doc = _load_json(path)
        receipt = _normalize_receipt(doc)
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
