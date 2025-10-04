from __future__ import annotations
from typing import Dict, Any, List
import os

from .schema import OcrResult, OcrPage, OcrBundle

def _extract_pages(upstage_json: Dict[str, Any]) -> List[OcrPage]:
    """
    Upstage 문서 구조 가정(견고성 보강):
    - pages: [ { text | blocks | lines | paragraphs | content }, ... ]
    - 없으면 최상위 text로 대체
    """
    pages: List[OcrPage] = []

    def _join_lines(blocks_like) -> str:
        lines = []
        for b in blocks_like or []:
            if isinstance(b, dict):
                # 가장 단순: block.text
                t = b.get("text")
                if isinstance(t, str) and t.strip():
                    lines.append(t)

                # lines 배열
                for ln in b.get("lines", []) or []:
                    if isinstance(ln, dict):
                        lt = ln.get("text")
                        if isinstance(lt, str) and lt.strip():
                            lines.append(lt)

                # paragraphs 배열
                for para in b.get("paragraphs", []) or []:
                    if isinstance(para, dict):
                        pt = para.get("text")
                        if isinstance(pt, str) and pt.strip():
                            lines.append(pt)

                # content(혼합형) 배열
                for seg in b.get("content", []) or []:
                    if isinstance(seg, dict):
                        st = seg.get("text")
                        if isinstance(st, str) and st.strip():
                            lines.append(st)
        return "\n".join(lines)

    if isinstance(upstage_json.get("pages"), list):
        for i, p in enumerate(upstage_json["pages"], start=1):
            txt = ""
            if isinstance(p, dict):
                # 우선순위: page-level text → blocks/lines/paragraphs/content
                if isinstance(p.get("text"), str):
                    txt = p["text"]
                elif "blocks" in p:
                    txt = _join_lines(p.get("blocks"))
                elif "lines" in p:
                    txt = _join_lines([{"lines": p.get("lines")}])
                elif "paragraphs" in p:
                    txt = _join_lines([{"paragraphs": p.get("paragraphs")}])
                elif "content" in p:
                    txt = _join_lines([{"content": p.get("content")}])
            pages.append(OcrPage(page=i, text=(txt or "").strip()))
    else:
        # fallback: 최상위 text만 있는 응답일 때
        full = upstage_json.get("text") or ""
        pages = [OcrPage(page=1, text=str(full).strip())]

    return pages

class OcrParser:
    def __init__(self, provider_client):
        self.client = provider_client

    def parse_file(self, filepath: str) -> OcrBundle:
        # 업스테이지에 넘길 filename은 basename이 더 깔끔
        basename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            raw = self.client.ocr(f, filename=basename)

        pages = _extract_pages(raw)
        full_text = "\n\n".join(p.text for p in pages if p.text)

        result = OcrResult(
            filename=basename,
            pages=pages,
            full_text=full_text.strip(),
            provider="upstage",
            model="ocr",
            meta={
                "page_count": len(pages),
                "language": raw.get("language"),
                "has_pages": "pages" in raw,
            },
        )
        return OcrBundle(result=result, raw=raw)
