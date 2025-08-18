# examples/parse_one_debug.py
from __future__ import annotations
import os, pathlib
from dotenv import load_dotenv

print(">>> enter debug runner")

# 1) .env 로드 + 키 존재 확인
load_dotenv()
print("API_KEY present?:", bool(os.getenv("UPSTAGE_API_KEY") or os.getenv("PARSER_API_KEY")))

# 2) 입력/출력 경로
inp = "data/policies-sample/부산대학교 총학생회 재정운용세칙.pdf"
out = "out/policies/부산.json"
print("inp:", inp)
print("out:", out)

# 3) 실제 호출
from lm_docparse.pdfParser import call_document_parse
print("→ calling call_document_parse ...")
call_document_parse(inp, out, verbose=True)
print("✓ done")