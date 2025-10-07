# -*- coding: utf-8 -*-
"""
apply_profile: 템플릿 HTML + 매핑 프로필을 받아 공통 Virtual View를 생성
- mode="budget"|"settlement" 에 따라 금액 컬럼(expected|actual) 스위칭
- 반환: {"rows":[{...}], "confidence": float, "meta": {...}}
"""
from __future__ import annotations
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import re

def _coerce_int(x) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return int(round(x))
        s = str(x).strip().replace(",", "")
        if s == "":
            return None
        return int(float(s))
    except Exception:
        return None

def _norm(s: str | None) -> str:
    return (s or "").strip()

def _headers_of(table) -> List[str]:
    first = table.find_all("tr")
    if not first:
        return []
    hrow = first[0]
    hdrs = [th.get_text(strip=True) for th in hrow.find_all(["th", "td"])]
    return [h.replace(" ", "") for h in hdrs]

def _find_best_table(soup: BeautifulSoup, mapping: Dict[str, str]) -> Optional[Any]:
    """매핑에 있는 '원본 헤더명'이 가장 많이 겹치는 <table> 선택."""
    targets = set([_norm(v).replace(" ", "") for v in (mapping or {}).values() if v])
    best = None
    best_score = -1
    for t in soup.find_all("table"):
        hdrs = _headers_of(t)
        if not hdrs:
            continue
        score = sum(1 for v in targets if v in hdrs)
        if score > best_score:
            best, best_score = t, score
    return best

def _index_map(table, mapping: Dict[str, str]) -> Dict[str, int]:
    """표준키→열 인덱스. 매핑에서 '원본 헤더명'으로 인덱스를 찾음."""
    hdrs = _headers_of(table)
    idx = {}
    for std_key, raw_name in (mapping or {}).items():
        if not raw_name:
            continue
        raw_norm = raw_name.replace(" ", "")
        try:
            i = hdrs.index(raw_norm)
            idx[std_key] = i
        except ValueError:
            # 간단 유연성: 괄호/원문 공백 제거 버전도 시도
            raw_norm2 = re.sub(r"[()\s]", "", raw_name)
            for j, h in enumerate(hdrs):
                if re.sub(r"[()\s]", "", h) == raw_norm2:
                    idx[std_key] = j
                    break
    return idx

def apply_profile(raw_html: str, profile: dict, mode: str = "settlement") -> dict:
    """
    입력: Raw HTML(Upstage), 매핑 Profile(JSON/YAML 파싱), mode
    출력: {"rows":[{"category":..., "amount":..., "amount_type":..., ...}, ...], "confidence": 0.8}
    """
    soup = BeautifulSoup(raw_html or "", "html.parser")
    rows_out: List[Dict[str, Any]] = []

    sections = (profile or {}).get("sections") or {}
    amount_key = "expected_amount" if mode == "budget" else "actual_amount"

    for section_name, section in sections.items():
        mapping: Dict[str, str] = section.get("mapping") or section  # 호환: 단순 dict도 허용
        table = _find_best_table(soup, mapping)
        if not table:
            continue

        idx = _index_map(table, mapping)
        tr_list = table.find_all("tr")[1:]  # 헤더 다음부터
        for r_idx, tr in enumerate(tr_list):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            def get(std_key: str) -> Optional[str]:
                j = idx.get(std_key)
                return cells[j] if (j is not None and j < len(cells)) else None

            amt = _coerce_int(get(amount_key))
            row = {
                "category": _norm(get("item")) or _norm(get("category")),
                "budget_code": _norm(get("budget_code")),
                "description": _norm(get("description")),
                "amount": amt,
                "amount_type": "expected" if mode == "budget" else "actual",
                "note": _norm(get("note")),
                "source": {"section": section_name, "row_index": r_idx}
            }
            # 최소 유효성: category/description/amount 중 하나라도 있으면 채택
            if any([row["category"], row["description"], row["amount"]]):
                rows_out.append(row)

    # confidence: 매우 단순 계산(행 수 기반)
    confidence = min(1.0, 0.15 * len(rows_out))

    virtual_view = {
        "rows": rows_out,
        "confidence": confidence,
        "meta": {
            "mode": mode,
            "template_id": profile.get("template_id"),
            "profile_name": profile.get("name"),
        }
    }
    return virtual_view
