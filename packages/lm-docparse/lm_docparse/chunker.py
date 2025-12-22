# packages/lm-docparse/lm_docparse/chunker.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import re, json, html, string
from typing import Any

MULTIPLY_SIGNS = r"[xX×＊*]"
_TAG_RE = re.compile(r"<[^>]+>")

# ★ NEW: 규정/세칙 전용 정규식
RE_CHAPTER = re.compile(r"^제\s*\d+\s*장\b")
RE_SECTION = re.compile(r"^제\s*\d+\s*절\b")
RE_SUBSEC  = re.compile(r"^제\s*\d+\s*관\b")
RE_ARTICLE = re.compile(r"^제\s*(\d+)\s*조\b")
RE_CLAUSE  = re.compile(r"^[（(]?\s*([①-⑳]|\d+)\s*[）).]")
RE_ITEM    = re.compile(r"^\s*(\d+)\.\s")
RE_PROVISO = re.compile(r"^부\s*칙(\s*\(.*?\))?")
RE_ANNEX   = re.compile(r"^\[(별표|별지)\s*([^\]]*)\]")
RE_VERSION = re.compile(r"^\[시행\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\]\[규약?\s*제?\s*([0-9]+)호.*?\]")

def _get_raw_html_from_content(cont: Any) -> str:
    if isinstance(cont, dict):
        h = cont.get("html")
        return h if isinstance(h, str) and h.strip() else ""
    if isinstance(cont, str) and "<table" in cont.lower():
        return cont
    return ""

def strip_html(s: str) -> str:
    s = s.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return _TAG_RE.sub(" ", s)

def hyphen_fix(text: str) -> str:
    return re.sub(r"-\s*\n\s*", "", text or "")

def coerce_text(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, str): return value
    if isinstance(value, dict):
        if "content" in value: return coerce_text(value["content"])
        for k in ("text", "markdown", "html"):
            v = value.get(k)
            if isinstance(v, str) and v.strip(): return v
        if isinstance(value.get("lines"), list):
            return "\n".join(coerce_text(x) for x in value["lines"])
        if isinstance(value.get("children"), list):
            return "\n".join(coerce_text(x) for x in value["children"])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(coerce_text(x) for x in value)
    return str(value)

def normalize_text(text_like: Any) -> str:
    s = coerce_text(text_like)
    if ("<" in s and ">" in s):
        s = strip_html(s)
    s = html.unescape(s)
    s = s.replace("\u00A0", " ")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = hyphen_fix(s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"\(\s*\n\s*", "(", s)
    s = re.sub(r"\s*\n\s*\)", ")", s)
    s = re.sub(r"([0-9][0-9,]*)\s*\n\s*(원|엔|円)", r"\1\2", s)
    s = re.sub(r"([0-9][0-9,]*)\s*\n\s*(개|회|건|명|일|%)", r"\1\2", s)
    s = re.sub(rf"\s*\n\s*({MULTIPLY_SIGNS})\s*\n\s*", r" \1 ", s)
    s = re.sub(rf"\s*\n\s*({MULTIPLY_SIGNS})\s*", r" \1 ", s)
    s = re.sub(rf"\s*{MULTIPLY_SIGNS}\s*", " x ", s)
    s = re.sub(r"(?<![\.!\?:;\]\)\}…])\n(?!\n)", " ", s)
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s

PUNCT_WS = set(string.punctuation) | {" ", "\n", "\t", "\r"}
def is_noise_chunk(title, text) -> bool:
    t = (text or "").strip()
    if not t: return True
    if len(t) < 5 and not (title and title.strip()): return True
    if all((ch in PUNCT_WS or ch.isdigit()) for ch in t): return True
    return False

# ★ NEW: 제목/본문에서 규정 계층 및 부속/버전 탐지
def detect_hierarchy(title: str, text: str) -> Dict[str, Optional[str]]:
    t = (title or "").strip()
    h = {"chapter":None,"section":None,"subsection":None,"article_no":None,"clause_no":None,"item_no":None}
    if RE_CHAPTER.search(t): h["chapter"] = t
    if RE_SECTION.search(t): h["section"] = t
    if RE_SUBSEC.search(t):  h["subsection"] = t
    m = RE_ARTICLE.search(t) or RE_ARTICLE.search(text or "")
    if m: h["article_no"] = f"제{m.group(1)}조"
    # 항/호는 본문 첫 줄에서만 가볍게 스캔
    first = (text or "").split("\n",1)[0]
    mc = RE_CLAUSE.match(first or "")
    if mc: h["clause_no"] = mc.group(1)
    mi = RE_ITEM.match(first or "")
    if mi: h["item_no"] = mi.group(1) + "."
    return h

def detect_annex(title: str) -> Tuple[bool, Optional[str]]:
    t = (title or "").strip()
    if not t: return (False, None)
    if RE_PROVISO.search(t): return (True, "proviso")
    ma = RE_ANNEX.search(t)
    if ma:
        kind = "annex_table" if "별표" in ma.group(0) else "annex_form"
        return (True, kind)
    return (False, None)

def detect_version_line(text: str) -> Optional[Dict[str,str]]:
    m = RE_VERSION.search(text or "")
    if not m: return None
    y, mo, d, no = m.groups()
    return {"effective_date": f"{int(y):04d}-{int(mo):02d}-{int(d):02d}", "promulgation_no": f"제{no}호"}

# ★ NEW: [별표 1] 등 테이블에서 자리 의미/라벨 추출(가능한 경우)
def extract_code_schema_from_tables(tables: List[Dict]) -> Optional[Dict]:
    """
    기대 헤더 예: '구분', '첫째 자리', '둘째 자리', '셋째 자리', '세부내역', '비고'
    값 예: '5 : 운영비' → {"1":{"5":"운영비"}, ...}
    """
    if not tables: return None
    pos = {"1":{}, "2":{}, "3":{}}
    found = False
    for tb in tables:
        rows = tb.get("rows") or []
        if not rows: continue
        # 헤더 후보 찾기
        header = [str(x) for x in rows[0]]
        header_join = " ".join(header)
        if ("첫째" in header_join and "셋째" in header_join) or ("자리" in header_join):
            # 본문 행 스캔
            for r in rows[1:]:
                cells = [str(x) for x in r]
                line = " ".join(cells)
                # '5 : 운영비' 같은 패턴들 긁기
                for idx, key in enumerate(["1","2","3"]):
                    m = re.search(r"([0-9])\s*[:：]\s*([^\s\|,;]+)", line)
                    if m:
                        pos[key][m.group(1)] = m.group(2)
                        found = True
    if not found:
        return None
    return {"digits":3, "position":{"1":{"name":"분야","values":pos["1"]},
                                     "2":{"name":"세부분야","values":pos["2"]},
                                     "3":{"name":"비목","values":pos["3"]}}}


def to_chunks(resp_json: Any, include_tables: bool = True) -> List[Dict]:
    out: List[Dict] = []
    adapter_seed: Optional[Dict] = None   # ★ NEW

    elements = None
    if isinstance(resp_json, dict) and isinstance(resp_json.get("elements"), list):
        elements = resp_json["elements"]

    if elements:
        stack_titles: List[str] = []
        # ★ NEW: 문서 머리의 버전(시행/규약번호)도 수집
        doc_version: Optional[Dict[str,str]] = None

        for i, el in enumerate(elements):
            cat  = el.get("category") or ""
            cont = el.get("content", {})
            title = None
            code  = el.get("id")
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
                    pass

            lvl = None
            m = re.match(r"heading(\d+)", str(cat))
            if m:
                lvl = max(1, min(int(m.group(1)), 6))
                title = text.split("\n", 1)[0] if text else None

            if lvl:
                if len(stack_titles) < lvl:
                    stack_titles += [""] * (lvl - len(stack_titles))
                stack_titles[lvl-1] = (title or "").strip()
                for j in range(lvl, len(stack_titles)):
                    stack_titles[j] = ""
            path_titles = [t for t in stack_titles if t]

            if is_noise_chunk(title, text):
                continue

            context = " > ".join(path_titles) if path_titles else (title or "")
            context_text = (context + " :: " + text[:400]) if context else text[:400]

            # ★ NEW: 규정 계층 / 부속 / 버전 탐지
            hierarchy = detect_hierarchy(title or "", text)
            is_annex, annex_type = detect_annex(title or "")
            if not doc_version:
                v = detect_version_line(text)
                if v: doc_version = v

            chunk = dict(
                order=el.get("id", i),
                code=code,
                title=title,
                text=text,
                path=(" > ".join(path_titles) if path_titles else None),
                context_text=context_text,
                hierarchy=hierarchy,                 # ★ NEW
                is_annex=is_annex,                   # ★ NEW
                annex_type=annex_type,               # ★ NEW
                version=doc_version                  # ★ NEW (문서 머리에만 세팅되면 그대로 공유)
            )

            # ★ NEW: 별표(코드표)면 어댑터 씨앗 추출
            if is_annex and annex_type in ("annex_table","annex_form") and not adapter_seed:
                if tables:
                    schema = extract_code_schema_from_tables(tables)
                    if schema:
                        adapter_seed = dict(code_system=schema, source_chunk=chunk.get("order"))

            if tables:
                chunk["tables"] = tables

            out.append(chunk)

        if out:
            out.sort(key=lambda x: x["order"])
            # ★ NEW: 맨 앞 청크에 씨앗 첨부(후단에서 한 번에 집어가도록)
            if adapter_seed and "__adapter_seed__" not in out[0]:
                out[0]["__adapter_seed__"] = adapter_seed
            return out

    # 이하 폴백 로직(원본 유지) ─────────────
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
        # ★ NEW: 폴백에도 최소 메타
        chunk["hierarchy"] = detect_hierarchy(None, whole)
        v = detect_version_line(whole);  chunk["version"] = v
        if tables:
            chunk["tables"] = tables
        return [chunk]

    # items 기반 폴백(원본 유지 + 소폭 보강) ─────────
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
                    path=None, context_text=whole[:400],
                    hierarchy=detect_hierarchy(None, whole), version=detect_version_line(whole))]

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
            context_text=context_text,
            hierarchy=detect_hierarchy(title or "", text),    # ★ NEW
            version=detect_version_line(text)                  # ★ NEW
        ))
    out.sort(key=lambda x: x["order"])
    return out
