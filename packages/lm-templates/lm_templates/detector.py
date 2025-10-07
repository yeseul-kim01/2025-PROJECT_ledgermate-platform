# -*- coding: utf-8 -*-
from bs4 import BeautifulSoup
from .schema import TemplateSchema, TableSchema, Column, HeaderField
from .normalize import CANON_MAP, HEADER_CANON_MAP

def detect_template_from_html(file_id: str, html: str) -> TemplateSchema:
    soup = BeautifulSoup(html, "html.parser")
    schema = TemplateSchema(file_id=file_id)

    # 1) 헤더 후보 감지
    for tag in soup.find_all(["p","div","span","strong"]):
        text = (tag.get_text() or "").strip()
        if ":" in text and len(text) < 40:
            k, _, v = text.partition(":")
            k = k.strip().replace(" ", "")
            v = v.strip()
            canonical = HEADER_CANON_MAP.get(k)
            if canonical:
                schema.detected_headers.append(HeaderField(raw_key=k, canonical=canonical, value_hint=v))

    # 2) 테이블 감지: 첫 행을 헤더로 보고 컬럼 표준화
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if not rows:
            continue
        headers = [th.get_text(strip=True) for th in rows[0].find_all(["th","td"])]
        if not headers:
            continue

        cols = []
        for i, h in enumerate(headers):
            h_norm = h.replace(" ", "")
            canonical = CANON_MAP.get(h_norm)
            cols.append(Column(raw_name=h, canonical=canonical or "", index=i))

        if sum(1 for c in cols if c.canonical) >= 2:
            schema.detected_tables.append(TableSchema(name="결산표", columns=cols))

    # 3) 신뢰도 간단 계산
    col_hits = sum(1 for t in schema.detected_tables for c in t.columns if c.canonical)
    schema.confidence = min(1.0, 0.2 * len(schema.detected_tables) + 0.05 * col_hits)
    return schema
