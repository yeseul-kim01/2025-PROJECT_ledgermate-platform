# packages/lm-docparse/lm_docparse/pdfParser.py
from __future__ import annotations

import os
import json
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# .env 먼저 로드 → 환경변수 읽기
load_dotenv()
API_KEY = os.getenv("UPSTAGE_API_KEY") or os.getenv("PARSER_API_KEY")
BASE = (os.getenv("PARSER_API_BASE") or "https://api.upstage.ai/v1").rstrip("/")
URL = f"{BASE}/document-digitization"


def _b(v: bool) -> str:
    """multipart/form-data로 보낼 때 불리언은 문자열로 포장"""
    return "true" if v else "false"


def call_document_parse(
    input_file: str,
    output_file: str,
    *,
    ocr: str = "force",                   # "force" | "auto"
    coordinates: bool = True,             # 좌표 필요 여부 (기본 True로 유지)
    chart_recognition: bool = True,       # 차트 인식
    output_formats: list[str] = ["html"], # "text", "markdown"도 가능
    base64_encoding: list[str] = ["table"],
    model: str = "document-parse",
    timeout: int = 120,
    verbose: bool = False,
) -> dict:

    if not API_KEY:
        raise RuntimeError("Set UPSTAGE_API_KEY (or PARSER_API_KEY) in .env")

    data = {
        "ocr": ocr,
        "coordinates": _b(coordinates),
        "chart_recognition": _b(chart_recognition),
        "output_formats": json.dumps(output_formats, ensure_ascii=False),
        "base64_encoding": json.dumps(base64_encoding, ensure_ascii=False),
        "model": model,
    }

    if verbose:
        size_kb = os.path.getsize(input_file) / 1024
        print(f"→ Upload: {input_file} ({size_kb:.1f} KB)")
        print(f"→ POST   {URL}")
        print(f"   opts  ocr={ocr} coord={coordinates} chart={chart_recognition} formats={output_formats}")

    t0 = time.perf_counter()
    with open(input_file, "rb") as f:
        resp = requests.post(
            URL,
            headers={"Authorization": f"Bearer {API_KEY}"},
            data=data,
            files={"document": (os.path.basename(input_file), f)},
            timeout=timeout,
        )
    elapsed = time.perf_counter() - t0

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        snippet = resp.text[:500]
        if verbose:
            print(f"✖ HTTP {resp.status_code} ({elapsed*1000:.0f} ms)")
            print(snippet)
        raise RuntimeError(f"[Upstage] HTTP {resp.status_code}: {snippet}") from e

    result = resp.json()

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)  # 폴더 자동 생성
    with out_path.open("w", encoding="utf-8") as w:
        json.dump(result, w, ensure_ascii=False, indent=2)

    if verbose:
        resp_kb = len(resp.content) / 1024
        print(f"✓ Saved  {out_path}  ({resp_kb:.1f} KB, {elapsed*1000:.0f} ms)")

    return result
