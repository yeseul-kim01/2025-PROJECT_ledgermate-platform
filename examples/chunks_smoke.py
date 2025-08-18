# examples/chunks_smoke.py
from __future__ import annotations
import json, sys, pathlib
from lm_docparse.chunker import to_chunks

def main(path: str = "out/policies/부산.json", show: int = 5) -> None:
    p = pathlib.Path(path)
    with p.open(encoding="utf-8") as f:
        obj = json.load(f)
    chs = to_chunks(obj)
    print(f"chunks: {len(chs)}")
    print("last 5 has text?:", [bool((c.get("text","") or "").strip()) for c in chs[-5:]])
    for c in chs[:show]:
        title = c.get("title") or ""
        text = c.get("text") or ""
        preview = (text[:80] + "…") if len(text) > 80 else text
        print(c.get("order"), title, "|", preview)

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "out/policies/부산.json"
    show = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    main(path, show)
