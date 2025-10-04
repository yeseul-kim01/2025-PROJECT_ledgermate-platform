from __future__ import annotations
import os, json
from typing import Dict, Any
from .schema import OcrBundle

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def save_bundle(bundle: OcrBundle, out_dir: str, basename: str) -> dict[str, str]:
    ensure_dir(out_dir)
    ocr_path = os.path.join(out_dir, f"{basename}.ocr.json")
    raw_path = os.path.join(out_dir, f"{basename}.raw.json")

    with open(ocr_path, "w", encoding="utf-8") as f:
        json.dump(bundle.result.model_dump(), f, ensure_ascii=False, indent=2)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(bundle.raw, f, ensure_ascii=False, indent=2)

    return {"ocr": ocr_path, "raw": raw_path}
