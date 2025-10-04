# examples/chunks_smoke.py
"""
LedgerMate — chunks_smoke.py

목적:
- 파서가 만든 JSON(정책/예산 파싱 결과) 1개를 받아
  to_chunks()로 '의미 청크'를 생성해보는 스모크 테스트.
- 청크 개수, 텍스트 유효성(마지막 5개), 앞부분 미리보기 출력으로
  청크 품질을 빠르게 확인한다.

입력:
- JSON 경로 (기본값: out/policies/부산.json)
  JSON은 lm_docparse 계열 파서가 만든 구조화 결과여야 함.

출력:
- 콘솔 로그:
  - "chunks: N"  : 생성된 청크 총 개수
  - "last 5 has text?: [True/False,...]" : 마지막 5개 청크의 text 필드 공백제거 후 존재 여부
  - 상위 show개(기본 5개)의 (order, title, text-preview) 한 줄 요약

사용 예:
  python examples/chunks_smoke.py
  python examples/chunks_smoke.py out/policies/rules_2025.json
  python examples/chunks_smoke.py out/policies/rules_2025.json 10   # 10개 미리보기

의존:
- lm_docparse.chunker.to_chunks : 파싱 JSON → 의미 청크 리스트 변환기
- JSON 인코딩은 UTF-8 가정

주의/팁:
- 입력 JSON이 파서 포맷이 아니면 to_chunks()가 기대대로 동작하지 않을 수 있음.
- text가 빈 청크가 많다면: normalize_text/분리 기준을 점검하거나 파서 단계(HTML→텍스트)가 제대로 됐는지 확인.
- order는 청크 정렬용 보조 값으로, 실제 DB 저장 시 ord 컬럼과 매칭되는 개념.

종료 코드:
- 파일 열기/JSON 디코딩 실패 시 예외 발생(트레이스 출력)
"""

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
