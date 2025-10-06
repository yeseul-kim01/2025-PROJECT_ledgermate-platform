from __future__ import annotations
import os, re, json, sys
from typing import Any, Dict, List, Tuple

def _strip(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()

def _is_code3(x: Any) -> bool:
    s = str(x)
    return s.isdigit() and len(s) == 3

_TOP_TITLE_RE = re.compile(r"[가-힣]\.\s*([^\(]+)\((\d{3})\)")
_FALLBACK_RE  = re.compile(r"([^\(]+)\((\d{3})\)")

def _top_title_to_name(title: str|None) -> str|None:
    if not title: return None
    m = _TOP_TITLE_RE.search(title) or _FALLBACK_RE.search(title)
    return _strip(m.group(1)) if m else _strip(title)

def extract_outline_from_budget_json(sections: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    sections: 너가 올린 예산안 JSON(list) 그대로 입력.
    return: [{"code":"711","path":"비정기 사업비>간식행사>상품비","label":"상품비"}, ...]
    """
    outline: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    current_top: str|None = None

    for sec in sections:
        # 섹션 제목에서 상위 사업분야명 추출 (예: "가. 운영비(500)" -> "운영비")
        title = sec.get("title")
        if title:
            top_name = _top_title_to_name(title)
            if any(k in title for k in ["운영비(", "정기사업비(", "비정기사업비(", "기타비용("]):
                current_top = top_name or current_top

        # 표가 없으면 패스
        for tbl in sec.get("tables", []):
            rows = tbl.get("rows") or []
            if not rows or len(rows) < 2:
                continue
            # 헤더 다음부터 데이터
            for r in rows[1:]:
                if not isinstance(r, list) or len(r) < 4:
                    continue
                # 표 형식 가정:
                # [세부코드, 세부이름, 비목코드, 비목이름, ...]
                sub_code, sub_name, item_code, item_name = r[0], r[1], r[2], r[3]
                if not (_is_code3(sub_code) and _is_code3(item_code)):
                    # 합계/빈줄 등 스킵
                    continue
                sub_name  = _strip(sub_name)
                item_name = _strip(item_name)
                top = current_top or ""
                path = f"{top}>{sub_name}>{item_name}".strip(">")
                code = str(item_code)
                label = item_name
                key = (code, path)
                if key in seen:
                    continue
                seen.add(key)
                outline.append({"code": code, "path": path, "label": label})

    return outline
def load_budget_outline(org_id: str) -> List[Dict[str, str]]:
    """
    data/<org_id>/budget_outline.json 로드
    """
    path = os.path.join("data", org_id, "budget_outline.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def outline_text(outline: List[Dict[str, str]]) -> str:
    """
    LLM 프롬프트용 보기 좋은 텍스트
    """
    if not outline:
        return "(코드표 없음)"
    lines = ["[예산 코드표] code | path | label"]
    for row in outline:
        lines.append(f"{row.get('code','')} | {row.get('path','')} | {row.get('label','')}")
    return "\n".join(lines)

def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()

def find_code_by_path(outline: List[Dict[str, str]], name_or_path: str) -> Optional[str]:
    """
    LLM이 낸 account_name(경로 또는 라벨)을 코드표에서 찾아 code 반환.
    1) path 정확매치 → 2) path 접미매치 → 3) label 매치
    """
    if not outline or not name_or_path:
        return None
    target = _norm(name_or_path)

    for row in outline:
        if _norm(row.get("path","")) == target:
            return str(row.get("code"))

    for row in outline:
        p = _norm(row.get("path",""))
        if p.endswith(target):
            return str(row.get("code"))

    for row in outline:
        if _norm(row.get("label","")) == target:
            return str(row.get("code"))

    return None

# ---------------------------
# CLI: json → budget_outline.json
# ---------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: python -m lm_settlement.extract_budget_outline <budget_json_path> <org_id> [<out_dir>]")
        sys.exit(1)
    in_path = sys.argv[1]
    org_id  = sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) >= 4 else os.path.join("data", org_id)

    with open(in_path, "r", encoding="utf-8") as f:
        sections = json.load(f)

    outline = extract_outline_from_budget_json(sections)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "budget_outline.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(outline, f, ensure_ascii=False, indent=2)
    print(f"✅ saved {len(outline)} entries → {out_path}")

if __name__ == "__main__":
    main()