# examples/policy_pdf_to_chunks.py
from __future__ import annotations
import os, json, re, argparse, hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY") or "YOUR_UPSTAGE_API_KEY"
UPSTAGE_BASE_URL = os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1")
DEFAULT_ORG_ID = os.getenv("ORG_ID", "demo.univ")

def sha256_bytes(b: bytes) -> str:
    import hashlib
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# examples/policy_pdf_to_chunks.py 내부

def upstage_parse_pdf(pdf_path: Path, model: str = "ocr") -> Dict[str, Any]:
    """
    Upstage Document Digitization 호출.
    model: "ocr" 권장. (parser는 이 엔드포인트에서 400이 납니다)
    """
    url = f"{UPSTAGE_BASE_URL}/document-digitization"
    headers = {"Authorization": f"Bearer {UPSTAGE_API_KEY}"}
    files = {"document": (pdf_path.name, pdf_path.read_bytes())}

    # 1차: ocr로 시도
    data = {"model": "ocr"}
    resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)
    if resp.status_code == 200:
        return resp.json()

    # 디버깅용 메시지 출력
    try:
        err = resp.json()
    except Exception:
        err = {"text": resp.text[:500]}

    # (선택) parser를 같은 엔드포인트에 보내면 400이므로 보내지 않음.
    raise requests.HTTPError(
        f"Upstage 400/BadRequest: document-digitization(model=ocr) 실패. "
        f"message={err}", response=resp
    )

# ---------- Heuristic extractors (응답 다양성 방어) ----------
_HEADING_RE = re.compile(r"^\s*([가-힣A-Za-z0-9]+[.)]|\d+[\-\.)])\s+(.+)$")
_CODE_RE = re.compile(r"\((\d{3,})\)")

def _try_pick(d: Dict[str, Any], keys: List[str], default=None):
    for k in keys:
        if k in d and d[k]:
            return d[k]
    return default

def extract_blocks(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Upstage 응답에서 '블록 텍스트'를 최대한 잘 뽑아내는 방어적 파서.
    우선순위: blocks/elements -> html/markdown -> text
    반환: [{"title":?, "path":?, "text":?...}, ...]
    """
    blocks: List[Dict[str, Any]] = []

    # 1) 구조화 블록 시도
    for key in ["blocks", "elements", "items"]:
        arr = parsed.get(key)
        if isinstance(arr, list) and arr:
            for it in arr:
                txt = _try_pick(it, ["text", "content", "value"], "").strip()
                if not txt:
                    continue
                title = _try_pick(it, ["title", "heading", "section_title"])
                path  = _try_pick(it, ["path", "section_path", "section"])
                blocks.append({"title": title, "path": path, "text": txt})
            if blocks:
                return blocks

    # 2) 마크다운/HTML 통짜 → 문단 분리
    md = _try_pick(parsed, ["markdown", "md"])
    html = _try_pick(parsed, ["html", "content_html", "document_html"])
    blob = md or html or _try_pick(parsed, ["text", "content"])
    if isinstance(blob, str) and blob.strip():
        paras = [p.strip() for p in re.split(r"\n{2,}", blob) if p.strip()]
        for p in paras:
            # (간이) 제목/코드/경로 추정
            m = _HEADING_RE.match(p.splitlines()[0])
            title = m.group(2).strip() if m else None
            code = None
            cm = _CODE_RE.search(p)
            if cm: code = cm.group(1)
            blocks.append({"title": title, "path": None, "text": p, "code": code})
        return blocks

    # 3) 실패 시 빈
    return blocks

def normalize_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for i, b in enumerate(blocks, 1):
        text = (b.get("text") or "").strip()
        if not text:
            continue
        title = b.get("title") or b.get("path")
        path  = b.get("path")
        out.append({
            "ord": i,
            "code": b.get("code"),
            "title": title,
            "path": path,
            "text": text,
        })
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True, help="세칙 PDF 경로")
    ap.add_argument("--org-id", default=DEFAULT_ORG_ID)
    ap.add_argument("--version", default=None, help="버전 문자열 (예: 2025.09). 미지정 시 v1")
    ap.add_argument("--model", default="parser", choices=["parser", "ocr"], help="Upstage 모델 선택")
    ap.add_argument("--out", default=None, help="출력 JSON 경로 (미지정 시 *.chunks.enriched.json)")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    assert pdf_path.exists(), f"파일 없음: {pdf_path}"

    parsed = upstage_parse_pdf(pdf_path, model=args.model)
    blocks = extract_blocks(parsed)
    chunks = normalize_blocks(blocks)

    version = args.version or "v1"
    file_sha = sha256_bytes(pdf_path.read_bytes())

    out_obj = {
        "meta": {
            "org_id": args.org_id,
            "version": version,
            "source_name": pdf_path.name,
            "file_sha": file_sha,
            "created_at": now_iso(),
            "normalized": True,
            "source": "upstage.document-digitization",
            "model": args.model,
        },
        "chunks": chunks,
    }

    if args.out:
        out_path = Path(args.out)
    else:
        out_path = pdf_path.with_suffix("").with_name(pdf_path.stem + ".chunks.enriched.json")
    out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ wrote {out_path} (chunks={len(chunks)})")
    print(f"   org_id={args.org_id} version={version} source={pdf_path.name}")

if __name__ == "__main__":
    main()
