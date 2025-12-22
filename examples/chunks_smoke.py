# examples/chunks_smoke.py (추가/수정)
from __future__ import annotations
import json, sys, pathlib
from lm_docparse.chunker import to_chunks

def main(path: str = "out/policies/부산.json", show: int = 5, write: bool = True) -> None:
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

    if write:
        outdir = pathlib.Path("out/chunks"); outdir.mkdir(parents=True, exist_ok=True)
        stem = p.stem
        out_jsonl = outdir / f"{stem}.chunks.jsonl"
        out_meta  = outdir / f"{stem}.meta.json"

        # 1) chunks.jsonl 저장
        with out_jsonl.open("w", encoding="utf-8") as fw:
            for ch in chs:
                fw.write(json.dumps(ch, ensure_ascii=False) + "\n")

        # 2) adapter_seed/meta 저장 (첫 청크에 실어둔 경우 분리 추출)
        meta = {}
        seed = chs[0].get("__adapter_seed__") if chs else None
        if seed:
            meta["adapter_seed"] = seed
        # 문서 레벨 버전/시행일 같은 것도 묶어서 보관(있으면)
        meta["version"] = chs[0].get("version") if chs else None

        with out_meta.open("w", encoding="utf-8") as fm:
            json.dump(meta, fm, ensure_ascii=False, indent=2)

        print(f"[write] {out_jsonl}")
        print(f"[write] {out_meta}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "out/policies/부산.json"
    show = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    # 세 번째 인자에 0/1로 write on/off
    write = bool(int(sys.argv[3])) if len(sys.argv) > 3 else True
    main(path, show, write)
