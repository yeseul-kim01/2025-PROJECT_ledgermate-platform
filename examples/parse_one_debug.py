# examples/parse_one_debug.py
"""
LedgerMate — parse_one_debug.py

목적:
- Upstage 문서 파서를 실제로 호출하여 PDF 1개를 파싱하고
  결과를 JSON 파일로 저장하는 디버그/스모크 테스트.

동작:
1) .env 로드 후 API 키 존재 여부 출력 (UPSTAGE_API_KEY 또는 PARSER_API_KEY)
2) 입력 PDF 경로(inp)와 출력 JSON 경로(out) 지정
3) call_document_parse(inp, out, verbose=True) 호출로 파싱 실행
4) 파싱 성공 시 out 경로에 JSON 생성, 콘솔에 진행 로그 출력

입출력:
- 입력: PDF 파일 1개 (하드코딩된 경로를 필요시 수정)
- 출력: 파싱 결과 JSON 1개 (out 경로, 디렉터리는 사전에 존재해야 함)
- DB 저장은 하지 않음

환경:
- .env 내 API 키 필요: UPSTAGE_API_KEY=sk-...  (선택) UPSTAGE_API_BASE
- 의존성: python-dotenv, requests 등 (requirements/dev.txt 참고)

자주 나는 이슈:
- 401 Unauthorized → API 키/결제 상태 확인
- FileNotFoundError → out 디렉터리 미생성 (미리 mkdir 필요)
- 경로/인코딩 문제 → 파일 경로를 절대경로로 변경하거나 OS 로케일 확인

팁:
- 하드코딩 대신 argparse로 입력/출력 경로 받도록 바꾸면 재사용성이 좋아짐.
- out 디렉터리 없으면 자동 생성하도록 pathlib.Path(out).parent.mkdir(..., exist_ok=True) 추가 권장.
"""


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