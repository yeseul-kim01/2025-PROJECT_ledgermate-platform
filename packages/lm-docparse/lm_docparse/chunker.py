# packages/lm-docparse/lm_docparse/chunker.py
from __future__ import annotations
from typing import Any, Dict, List
import re, json, html, string
from typing import Any

MULTIPLY_SIGNS = r"[xX×＊*]"
# ── helpers ─────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")

def _get_raw_html_from_content(cont: Any) -> str:
    if isinstance(cont, dict):
        h = cont.get("html")
        return h if isinstance(h, str) and h.strip() else ""
    if isinstance(cont, str) and "<table" in cont.lower():
        return cont
    return ""


def strip_html(s: str) -> str:
    # <br> → 개행 보존 후 태그 제거
    s = s.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return _TAG_RE.sub(" ", s)

def hyphen_fix(text: str) -> str:
    return re.sub(r"-\s*\n\s*", "", text or "")

def coerce_text(value: Any) -> str:
    """dict/list/str 어떤 형태든 '의미 있는 텍스트'로 변환.
       text가 비어있으면 markdown→html로 ‘폴백’한다."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # 1) content 래퍼 처리
        if "content" in value:
            return coerce_text(value["content"])
        # 2) 우선순위: non-empty text → markdown → html
        for k in ("text", "markdown", "html"):
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                return v
        # 3) lines/children 합치기
        if isinstance(value.get("lines"), list):
            return "\n".join(coerce_text(x) for x in value["lines"])
        if isinstance(value.get("children"), list):
            return "\n".join(coerce_text(x) for x in value["children"])
        # 4) 마지막 폴백: JSON 보존(디버그용)
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(coerce_text(x) for x in value)
    return str(value)


def normalize_text(text_like: Any) -> str:
    s = coerce_text(text_like)
    if ("<" in s and ">" in s):            # HTML 추정
        s = strip_html(s)
    s = html.unescape(s)

    # 1) 공백/개행 기초 정리
    s = s.replace("\u00A0", " ")           # NBSP → space
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = hyphen_fix(s)                      # 단어 하이픈 줄바꿈 복원 (이미 있던 함수)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)       # 3줄 이상 → 2줄

    # 2) 괄호/단위가 개행으로 깨진 케이스 복원
    #   예: "예산액(\n원)" → "예산액(원)"
    s = re.sub(r"\(\s*\n\s*", "(", s)
    s = re.sub(r"\s*\n\s*\)", ")", s)

    #   예: "1,200,000\n원" / "70\n개" / "2\n회" / "10\n%" → 한 줄로
    s = re.sub(r"([0-9][0-9,]*)\s*\n\s*(원|엔|円)", r"\1\2", s)
    s = re.sub(r"([0-9][0-9,]*)\s*\n\s*(개|회|건|명|일|%)", r"\1\2", s)

    #   곱하기 표현이 줄바꿈으로 끊긴 경우: "5,000원 X \n 70개 X \n 2회"
    s = re.sub(rf"\s*\n\s*({MULTIPLY_SIGNS})\s*\n\s*", r" \1 ", s)  # 사이에 낀 개행 제거
    s = re.sub(rf"\s*\n\s*({MULTIPLY_SIGNS})\s*", r" \1 ", s)       # 앞뒤 공백 정리

    # 3) 곱하기 기호 통일(검색/파싱 안정화)
    s = re.sub(rf"\s*{MULTIPLY_SIGNS}\s*", " x ", s)

    # 4) 문장 중간의 애매한 1줄 개행 → 공백으로 합치기
    #   - 끝 문자가 문장부호가 아니고(.,!?…): 다음 줄이 이어지는 텍스트로 보아 붙임
    #   - 단, 빈 줄(단락 구분)은 유지
    s = re.sub(r"(?<![\.!\?:;\]\)\}…])\n(?!\n)", " ", s)

    # 5) 다시 여분 공백 최소화
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


PUNCT_WS = set(string.punctuation) | {" ", "\n", "\t", "\r"}
def is_noise_chunk(title, text) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if len(t) < 5 and not (title and title.strip()):
        return True
    if all((ch in PUNCT_WS or ch.isdigit()) for ch in t):
        return True
    return False

# ── main ────────────────────────────────────────────────────────────────

def to_chunks(resp_json: Any, include_tables: bool = True) -> List[Dict]:
    """
    Upstage 응답 → 균일한 청크 스키마:
    [{order, code, title, text, path, context_text}]
    """
    out: List[Dict] = []

    # 0) elements가 있으면 그걸 우선 사용 (heading 레벨로 path 구성)
    elements = None
    if isinstance(resp_json, dict) and isinstance(resp_json.get("elements"), list):
        elements = resp_json["elements"]

    if elements:
        stack_titles: List[str] = []
        for i, el in enumerate(elements):
            cat  = el.get("category") or ""
            cont = el.get("content", {})
            title = None
            code  = el.get("id")  # 명시적 조항번호가 없으니 id를 보조키로
            text  = normalize_text(cont)

            raw_html = _get_raw_html_from_content(cont)
            tables = None
            if include_tables and raw_html and "<table" in raw_html.lower():
                try:
                    from .tables import extract_tables_from_html, table_to_text
                    ts = extract_tables_from_html(raw_html)
                    if ts:
                        tables = ts
                        flat = "\n\n".join(table_to_text(t["rows"]) for t in ts if t.get("rows")).strip()
                        if flat:
                            text = (text + ("\n\n" if text else "") + flat).strip()
                except Exception:
                    # 표 추출 실패 시 조용히 건너뛴다(호환성)
                    pass

            # heading 레벨 추론 (heading1/2/3…)
            lvl = None
            m = re.match(r"heading(\d+)", str(cat))
            if m:
                lvl = max(1, min(int(m.group(1)), 6))
                # 제목은 heading 텍스트 전부
                title = text.split("\n", 1)[0] if text else None

            # path(부모 타이틀) 구성
            if lvl:
                if len(stack_titles) < lvl:
                    stack_titles += [""] * (lvl - len(stack_titles))
                stack_titles[lvl-1] = (title or "").strip()
                # 하위 레벨 비우기
                for j in range(lvl, len(stack_titles)):
                    stack_titles[j] = ""
            path_titles = [t for t in stack_titles if t]

            if is_noise_chunk(title, text):
                continue

            context = " > ".join(path_titles) if path_titles else (title or "")
            context_text = (context + " :: " + text[:400]) if context else text[:400]


            chunk = dict(
                order=el.get("id", i),
                code=code,
                title=title,
                text=text,
                path=(" > ".join(path_titles) if path_titles else None),
                context_text=context_text
            )
            if tables:
                chunk["tables"] = tables
                
            out.append(chunk)


        # 내용이 하나도 안 남았으면 폴백으로 내려감
        if out:
            out.sort(key=lambda x: x["order"])
            return out

    # 1) 폴백: content.html 전체를 통짜로
    if isinstance(resp_json, dict) and isinstance(resp_json.get("content"), dict):
        whole = normalize_text(resp_json["content"])
        raw_html = _get_raw_html_from_content(resp_json["content"])
        tables = None
        if include_tables and raw_html and "<table" in raw_html.lower():
            try:
                from .tables import extract_tables_from_html, table_to_text
                ts = extract_tables_from_html(raw_html)
                if ts:
                    tables = ts
                    flat = "\n\n".join(table_to_text(t["rows"]) for t in ts if t.get("rows")).strip()
                    if flat:
                        whole = (whole + ("\n\n" if whole else "") + flat).strip()
            except Exception:
                pass
        chunk = dict(order=0, code=None, title=None, text=whole, path=None, context_text=whole[:400])
        if tables:
            chunk["tables"] = tables
        return [chunk]

    # 2) 또 다른 폴백: 기존 탐색(keys)
    items = None
    if isinstance(resp_json, list):
        items = resp_json
    elif isinstance(resp_json, dict):
        for k in ("sections", "chunks", "items", "elements", "nodes"):
            if isinstance(resp_json.get(k), list):
                items = resp_json[k]; break
    if items is None:
        whole = normalize_text(resp_json)
        return [dict(order=0, code=None, title=None, text=whole,
                    path=None, context_text=whole[:400])]

    # (거의 오지 않지만) items 기반 생성
    stack_titles: List[str] = []
    for i, it in enumerate(items):
        code  = it.get("code") or it.get("number") or it.get("id")
        title = it.get("title") or it.get("heading") or it.get("name")
        text  = normalize_text(it)
        if is_noise_chunk(title, text):
            continue

        level = 1
        if isinstance(code, str) and code:
            level = min(len([p for p in code.split(".") if p]), 6)
        if title:
            if len(stack_titles) < level:
                stack_titles += [""] * (level - len(stack_titles))
            stack_titles[level-1] = title
            for j in range(level, len(stack_titles)):
                stack_titles[j] = ""
        path_titles = [t for t in stack_titles[:level] if t]

        context = " > ".join(path_titles) if path_titles else (title or "")
        context_text = (context + " :: " + text[:400]) if context else text[:400]

        out.append(dict(
            order=it.get("order") or it.get("index") or i,
            code=code, title=title, text=text,
            path=(" > ".join(path_titles) if path_titles else None),
            context_text=context_text
        ))

    out.sort(key=lambda x: x["order"])
    return out
